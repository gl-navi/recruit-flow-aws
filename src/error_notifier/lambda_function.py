"""Error notifier Lambda. Placeholder: the real behavior is built in WBS 7."""

import json

from shared import VERSION


def lambda_handler(event, context):
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"function": "error_notifier", "shared_version": VERSION}),
    }
