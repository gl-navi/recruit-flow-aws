# recruit-flow-aws

Recruitment application flow, moved from Pipedream to AWS. It connects the recruitment website forms to Salesforce, SharePoint, Slack and Marketo.

Planning documents (kept outside this repo): *Pipedream to AWS Migration Notes* and *Pipedream to AWS Migration WBS*.

## Layout

| Path | What it is |
| --- | --- |
| `src/receiver/` | Receiver Lambda: front door for the forms (WBS 5.1) |
| `src/worker/` | Worker Lambda: runs the six form flows (WBS 5.2 to 5.4) |
| `src/marketo_sync/` | Marketo score sync Lambda, started by a schedule (WBS 6) |
| `src/error_notifier/` | Error notifier Lambda (WBS 7) |
| `src/shared/` | Code shared by all Lambdas: Salesforce, Graph and Slack clients, helpers, step logging (WBS 4) |
| `config/environments.json` | Which AWS profile and function names belong to `dev` and `prod` |
| `scripts/` | `deploy.sh` and `build_zip.py` |
| `tests/` | Local tests |
| `docs/runbook.md` | What was created in AWS by hand, so it can be rebuilt |

Every Lambda is a `lambda_function.py` with a `lambda_handler`. Each deployed zip also contains the `shared/` package, so handlers can `from shared import ...`.

## Environments

- `dev`: the test copy. It points at the Salesforce sandbox.
- `prod`: the real copy. It points at real Salesforce and real applicants.

The names come from `config/environments.json`. The region there (`ap-northeast-1`) is still to be confirmed (WBS 2.1).

## Requirements

- Python 3.14 everywhere: local work, the Lambda runtime and, later, the worker's container base image (WBS 1.2). Keep the same version in all three. The code needs 3.12 or newer, because it uses syntax that older versions reject.
- AWS CLI v2 with one profile, `recruit` (dev and prod share it; they differ by function name). Check it with `aws sts get-caller-identity --profile recruit`.
- Git.
- Docker, to build the worker's container image (WBS 1.2).

## Run the tests

```bash
python3 -m unittest discover -s tests
```

## Deploy

```bash
scripts/deploy.sh <receiver|worker|marketo_sync|error_notifier> <dev|prod> [--dry-run]
```

- `--dry-run` builds the package without calling AWS: a zip in `build/` for the zip functions, a local Docker image for the worker.
- Deploying to `prod` asks you to type the function name first.
- **Zip functions** (`receiver`, `marketo_sync`, `error_notifier`): the script zips the function's folder plus `src/shared/` and uploads it.
- **Worker** (container image): the script builds `src/worker/Dockerfile`, pushes the image to the ECR repository named in `config/environments.json`, then points the Lambda function at it. The image tag is `build-<UTC date-time>`.
- To deploy an image that is already in ECR without rebuilding (for example to put the tested dev image on prod), set `IMAGE_TAG`:

```bash
IMAGE_TAG=build-20261014-071108 scripts/deploy.sh worker prod
```

- The worker functions must be created in the Lambda console with the **Container image** option. A function created from a normal Python runtime cannot be switched to an image later.
- It deploys code only. AWS resources (S3, Secrets Manager, ECR, schedules, permissions) are created by hand and written down in `docs/runbook.md`.

## Do not commit

Passwords, tokens, `.env` files, applicant data, or anything exported from Pipedream. The `.gitignore` blocks the common cases, but check before you commit.
