# Runbook: what was created in AWS

CloudFormation is not used for now, so every AWS resource is created by hand. Write each one down here as you create it, so it can be rebuilt. Never write secret values in this file.

## Access

| Item | Dev | Prod |
| --- | --- | --- |
| AWS account | TBD | TBD |
| Region | TBD (config says ap-northeast-1) | TBD |
| CLI profile | `recruit-dev` | `recruit-prod` |

## Lambda functions

Created as empty Python 3.14 "hello world" functions first (WBS 1.1). The worker moves to a container image in WBS 1.2.

| Function | Dev name | Prod name | Execution role | Created |
| --- | --- | --- | --- | --- |
| Receiver | `recruit-receiver-dev` | `recruit-receiver-prod` | TBD | |
| Worker | `recruit-worker-dev` | `recruit-worker-prod` | TBD | |
| Marketo sync | `recruit-marketo-sync-dev` | `recruit-marketo-sync-prod` | TBD | |
| Error notifier | `recruit-error-notifier-dev` | `recruit-error-notifier-prod` | TBD | |

## Other resources

| Resource | Name | Notes |
| --- | --- | --- |
| S3 bucket (uploads) | TBD | CORS for browser upload, auto-delete after a few days (WBS 1.3) |
| Secrets Manager secrets | TBD | Salesforce, Microsoft, Slack, Marketo (names only, never values) |
| EventBridge schedule | TBD | Marketo sync, every 10 minutes (WBS 6) |
| CloudWatch alarm and SNS topic | TBD | WBS 1.4 |
