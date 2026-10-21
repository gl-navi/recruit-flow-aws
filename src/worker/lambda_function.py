"""Worker Lambda. Placeholder: the real behavior is built in WBS 5.2 to 5.4."""

import json

from shared import VERSION

TEST_SLACK_CHANNEL = "C0CBDMFLHLY"
TEST_SLACK_USER = "U0BMD8T0Q2U"


def lambda_handler(event, context):
    if isinstance(event, dict) and event.get("slack_test"):
        from shared.slack_helper import SlackClient

        sent = SlackClient.from_secrets().post_message(
            event.get("slack_channel", TEST_SLACK_CHANNEL),
            "テスト: AWS Lambdaから送信しました",
            mentions=[event.get("slack_user", TEST_SLACK_USER)],
        )
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"function": "worker", "slack": sent}),
        }

    if isinstance(event, dict) and event.get("slack_file_test"):
        from shared.s3_helper import read_file
        from shared.slack_helper import SlackClient

        if event.get("s3_url"):
            file_name, file_content = read_file(event["s3_url"])
        else:
            file_name, file_content = "test.txt", "テスト用ファイルです".encode("utf-8")

        slack = SlackClient.from_secrets()
        channel = event.get("slack_channel", TEST_SLACK_CHANNEL)
        message = slack.post_message(
            channel,
            "テスト: ファイルを送ります",
            mentions=[event.get("slack_user", TEST_SLACK_USER)],
        )
        uploaded = slack.upload_file(
            channel,
            file_name,
            file_content,
            comment="テスト用ファイル",
            thread_ts=message["ts"],
        )
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"function": "worker", "slack": message, "file": uploaded}),
        }

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"function": "worker", "shared_version": VERSION}),
    }
