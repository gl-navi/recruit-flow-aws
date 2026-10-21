"""Receiver Lambda. Placeholder: the real behavior is built in WBS 5.1."""

import json

from shared import VERSION
from shared.log_helper import StepLogger


def lambda_handler(event, context):
    log = StepLogger(
        flow="test",
        function=getattr(context, "function_name", None),
        request_id=getattr(context, "aws_request_id", None),
    )

    log.info("receiver started")
    with log.step("receive_event", input=event) as step:
        log.info("event received")
        if event == {}:
            log.warning("event is empty")
        if isinstance(event, dict) and event.get("fail"):
            log.error("failure requested by the event")
            raise ValueError("test failure requested by the event")
        step.output = {"keys": sorted(event) if isinstance(event, dict) else None}

    with log.step("build_response") as step:
        response = {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"function": "receiver", "shared_version": VERSION}),
        }
        step.output = {"statusCode": response["statusCode"]}
    return response
