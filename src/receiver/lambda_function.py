"""Receiver Lambda. Placeholder: the real behavior is built in WBS 5.1."""

import json

from shared import VERSION


def lambda_handler(event, context):
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"function": "receiver", "shared_version": VERSION}),
    }
