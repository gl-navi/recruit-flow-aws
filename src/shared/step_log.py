"""Step logging helper (WBS 4.4).

Writes JSON lines to the Lambda's log (one log group), so CloudWatch Logs
Insights can search them. There are two kinds of line, told apart by "type":

  "message"  one per call to log.info / log.warning / log.error 
  "step"     one per finished step, with input and output 

    log = StepLogger(flow="HP", function="worker", request_id=context.aws_request_id)
    with log.step("validate_form_data", input=form_data) as step:
        log.info("checking required fields")
        result = validate(form_data)
        step.output = result

Secrets are masked and long values are cut before anything is written.
"""

import json
import time
import uuid
from contextlib import contextmanager

MAX_STRING = 200
MAX_ITEMS = 50
MAX_DEPTH = 6


def redact(value, key=None, depth=0):
    """Return a copy of value that is safe and short enough to log."""
    if depth > MAX_DEPTH:
        return "..."
    if isinstance(value, dict):
        return {str(k): redact(v, k, depth + 1) for k, v in list(value.items())[:MAX_ITEMS]}
    if isinstance(value, (list, tuple)):
        return [redact(v, None, depth + 1) for v in list(value)[:MAX_ITEMS]]
    if isinstance(value, (bytes, bytearray)):
        return f"<{len(value)} bytes>"
    if isinstance(value, str):
        if len(value) <= MAX_STRING:
            return value
        return f"{value[:MAX_STRING]}...(+{len(value) - MAX_STRING} chars)"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:MAX_STRING]


class StepRecord:
    """Set .output inside the `with` block to log what the step produced."""

    output = None


class StepLogger:
    # Attributes and log line fields, with example values:
    #
    #   type          "step" or "message"
    #   function      "recruit-worker", "recruit-receiver"
    #   flow          "HP", "新卒説明会前", "demo"
    #   request_id    "09e437e4-56ae-4da9-bd9c-ce01f600867e" (Lambda gives it)
    #   step          "check_record_exists" (kept in _current_step while it runs)
    #   seq_message   1, 2, 3 ... (counts message lines in one run) (message type only)
    #   seq_step      1, 2, 3 ... (counts step lines in one run)    (step type only)
    #   status        "ok" or "error"                (step type only)
    #   duration_ms   412                            (step type only)
    #   input         {"email": "a@example.com"}     (step type only)
    #   output        {"id": "a2qRB000003pOEfYAM"}   (step type only)
    #   error         "ValueError: boom"             (step type only, on failure)
    #   level         "INFO", "WARNING" or "ERROR"   (message type only)
    #   message       "create_new_record: True"      (message type only)

    def __init__(self, flow, function=None, request_id=None):
        self.flow = flow
        self.function = function
        self.request_id = request_id or uuid.uuid4().hex[:12]
        self._current_step = None
        self._seq_message = 0
        self._seq_step = 0

    def info(self, message):
        self._message("INFO", message)

    def warning(self, message):
        self._message("WARNING", message)

    def error(self, message):
        self._message("ERROR", message)

    @contextmanager
    def step(self, name, input=None):
        previous_step = self._current_step
        self._current_step = name
        record = StepRecord()
        started = time.perf_counter()
        try:
            yield record
        except Exception as exc:
            self._step_line(name, "error", started, input, record.output, f"{type(exc).__name__}: {exc}")
            raise
        else:
            self._step_line(name, "ok", started, input, record.output)
        finally:
            self._current_step = previous_step

    def _base(self, line_type):
        return {
            "type": line_type,
            "function": self.function,
            "flow": self.flow,
            "request_id": self.request_id,
            "step": self._current_step,
        }

    def _message(self, level, message):
        line = self._base("message")
        line["level"] = level
        line["message"] = redact(message)
        self._write(line)

    def _step_line(self, name, status, started, input, output, error=None):
        line = self._base("step")
        line["step"] = name
        line["status"] = status
        line["duration_ms"] = round((time.perf_counter() - started) * 1000)
        line["input"] = redact(input)
        line["output"] = redact(output)
        if error is not None:
            line["error"] = redact(error)
        self._write(line)

    def _write(self, line):
        # Message lines and step lines each have their own counter.
        if line["type"] == "message":
            self._seq_message += 1
            line = {"seq_message": self._seq_message, **line}
        else:
            self._seq_step += 1
            line = {"seq_step": self._seq_step, **line}
        # print() goes to CloudWatch Logs
        print(json.dumps(line, ensure_ascii=False, default=str))
