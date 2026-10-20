"""Worker Lambda. Placeholder: the real behavior is built in WBS 5.2 to 5.4."""

import json

from shared import VERSION


def lambda_handler(event, context):
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"function": "worker", "shared_version": VERSION}),
    }
