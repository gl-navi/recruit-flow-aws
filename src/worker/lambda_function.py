"""Worker Lambda. Placeholder: the real behavior is built in WBS 5.2 to 5.4."""

import base64
import json

from shared import VERSION


def detect_file_type(data):
    """Detect a file's MIME type the way the Pipedream check_file_type step did."""
    import magic  # imported here so the unit tests do not need libmagic

    path = "/tmp/magic_check_file"
    with open(path, "wb") as f:
        f.write(data)
    return magic.Magic(mime=True).from_file(path)


def lambda_handler(event, context):
    # TEMPORARY (WBS 1.2): proves libmagic works inside the Lambda image.
    # Remove this block when the real worker is built (WBS 5.2).
    if isinstance(event, dict) and "magic_check_base64" in event:
        detected = detect_file_type(base64.b64decode(event["magic_check_base64"]))
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"function": "worker", "detected_type": detected}),
        }

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"function": "worker", "shared_version": VERSION}),
    }
