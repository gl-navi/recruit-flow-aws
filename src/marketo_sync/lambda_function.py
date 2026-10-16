"""Marketo sync Lambda. Placeholder: the real behavior is built in WBS 6."""

import json

from shared import VERSION


def lambda_handler(event, context):
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"function": "marketo_sync", "shared_version": VERSION}),
    }
