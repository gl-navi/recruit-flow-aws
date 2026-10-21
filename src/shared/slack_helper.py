"""Slack client for posting notifications

Posts one message to one channel with the bot token. The channel and the people
to tag are passed in by the caller.

    slack = SlackClient.from_secrets()
    message = slack.post_message("C0123456789", "New applicant", mentions=["U0123456789"])
    slack.upload_file("C0123456789", "resume.pdf", file_bytes, thread_ts=message["ts"])

"""

import time

import httpx
from tenacity import Retrying, retry_if_exception, stop_after_attempt

from shared.secrets_helper import get_secrets

SLACK_API_URL = "https://slack.com/api"
RETRY_STATUSES = {408, 429, 500, 502, 503, 504}
RETRYABLE_SLACK_ERRORS = {"ratelimited", "internal_error", "service_unavailable", "fatal_error"}
MAX_ATTEMPTS = 3
RETRY_DELAY = 2  # seconds
MAX_RETRY_AFTER = 30  # never wait longer than this, even if Slack asks for more

# What to check for the Slack error codes seen most often.
ERROR_HINTS = {
    "invalid_auth": "the bot token is not valid. Check SLACK_BOT_TOKEN.",
    "not_authed": "no bot token was sent. Check SLACK_BOT_TOKEN.",
    "token_revoked": "the bot token was revoked. Make a new one in the Slack app.",
    "token_expired": "the bot token expired. Make a new one in the Slack app.",
    "account_inactive": "the app or its token is deactivated.",
    "missing_scope": "the app lacks a permission. Messages need chat:write, files need files:write.",
    "channel_not_found": "check the channel ID, and invite the bot if the channel is private.",
    "not_in_channel": "the bot is not in the channel. Invite it with /invite.",
    "is_archived": "the channel is archived.",
    "msg_too_long": "the message text is too long.",
    "no_text": "the message has no text.",
    "invalid_blocks": "the message blocks are not valid.",
    "ratelimited": "Slack is rate limiting the bot. Try again later.",
}


class SlackError(Exception):
    """Slack refused or could not post. .code is Slack's error code (or http_<status>)."""

    def __init__(self, code, channel="", detail=""):
        hint = ERROR_HINTS.get(code, detail)
        super().__init__(f"Slack error '{code}' for channel {channel}: {hint}".rstrip(": "))
        self.code = code


def _is_retryable(exc):
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRY_STATUSES
    if isinstance(exc, SlackError):
        return exc.code in RETRYABLE_SLACK_ERRORS
    return False


def _wait(retry_state):
    exc = retry_state.outcome.exception()
    if isinstance(exc, httpx.HTTPStatusError):
        retry_after = exc.response.headers.get("Retry-After", "")
        if retry_after.isdigit():
            return min(int(retry_after), MAX_RETRY_AFTER)
    return RETRY_DELAY


def _with_mentions(text, mentions):
    """Put <@USERID> tags in front of the text. mentions is one user ID or a list."""
    if isinstance(mentions, str):
        mentions = [mentions]
    if not mentions:
        return text
    return " ".join(f"<@{user_id}>" for user_id in mentions) + " " + text


class SlackClient:
    def __init__(
        self,
        token,
        *,
        timeout=15,
        transport=None,
        sleep=time.sleep,
    ):
        self._token = token
        self._sleep = sleep
        self._http = httpx.Client(timeout=timeout, transport=transport)

    @classmethod
    def from_secrets(cls, **kwargs):
        return cls(get_secrets(["SLACK_BOT_TOKEN"])["SLACK_BOT_TOKEN"], **kwargs)

    def post_message(self, channel, text, *, mentions=None, blocks=None):
        payload = {"channel": channel, "text": _with_mentions(text, mentions)}
        if blocks:
            payload["blocks"] = blocks
        data = self._api("chat.postMessage", channel, json_body=payload)
        return {"channel": data.get("channel"), "ts": data.get("ts")}

    def upload_file(self, channel, filename, content, *, title=None, comment=None, mentions=None, thread_ts=None):
        """Upload a file (bytes) to a channel and return {"file_id": ..., "name": ...}.

        Slack uploads a file in three calls: ask for an upload address, send the
        bytes to it, then finish and share the file in the channel. Needs the
        files:write permission. thread_ts puts the file in the thread of a message
        that post_message returned. comment is the text shown with the file.
        """
        started = self._api("files.getUploadURLExternal", channel, form={"filename": filename, "length": len(content)})
        self._retrying(lambda: self._send_bytes(started["upload_url"], content), channel)

        payload = {"files": [{"id": started["file_id"], "title": title or filename}], "channel_id": channel}
        if comment:
            payload["initial_comment"] = _with_mentions(comment, mentions)
        if thread_ts:
            payload["thread_ts"] = thread_ts
        self._api("files.completeUploadExternal", channel, json_body=payload)
        return {"file_id": started["file_id"], "name": filename}

    def _api(self, method, channel, *, json_body=None, form=None):
        """Call one Slack API method and return its reply, or raise SlackError."""

        def call():
            headers = {"Authorization": f"Bearer {self._token}"}
            if json_body is not None:
                headers["Content-Type"] = "application/json; charset=utf-8"
            response = self._http.post(
                f"{SLACK_API_URL}/{method}", json=json_body, data=form, headers=headers
            )
            response.raise_for_status()
            data = response.json()
            if not data.get("ok"):
                raise SlackError(data.get("error", "unknown_error"), channel)
            return data

        return self._retrying(call, channel)

    def _send_bytes(self, upload_url, content):
        response = self._http.post(upload_url, content=content, headers={"Content-Type": "application/octet-stream"})
        response.raise_for_status()

    def _retrying(self, action, channel):
        """Run action(), retrying network errors, 408, 429, 5xx and Slack's rate limit."""
        try:
            for attempt in Retrying(
                stop=stop_after_attempt(MAX_ATTEMPTS),
                wait=_wait,
                retry=retry_if_exception(_is_retryable),
                sleep=self._sleep,
                reraise=True,
            ):
                with attempt:
                    return action()
        except httpx.HTTPStatusError as exc:
            raise SlackError(f"http_{exc.response.status_code}", channel, exc.response.text[:200]) from exc
