"""Secrets lookup, written for Lambda.

For every name the order is: AWS Secrets Manager first, then environment
variables, then the name is reported as missing.

    secrets = get_secrets(["MS_TENANT_ID", "MS_CLIENT_SECRET"])
    secrets["MS_TENANT_ID"]
"""

import json
import os

SECRET_NAME_VARIABLE = "SECRET_NAME"

# One Lambda container keeps its secrets after the first read, so Secrets
# Manager is called once per container, not once per request.
_secret_cache = {}


def _read_secret(secret_name):
    if secret_name not in _secret_cache:
        # boto3 is included in Lambda. to read secrets manager
        import boto3

        try:
            response = boto3.client("secretsmanager").get_secret_value(SecretId=secret_name)
        except Exception as exc:
            raise RuntimeError(f"Could not read the secret '{secret_name}' from Secrets Manager: {exc}") from exc
        _secret_cache[secret_name] = json.loads(response["SecretString"])
    return _secret_cache[secret_name]


def get_secrets(names):
    """Return {name: value} for every name, or raise RuntimeError listing the missing ones."""
    secret_name = os.environ.get(SECRET_NAME_VARIABLE)
    secret = _read_secret(secret_name) if secret_name else {}

    values = {}
    missing = []
    for name in names:
        value = secret.get(name) or os.environ.get(name)
        if value:
            values[name] = str(value)
        else:
            missing.append(name)
    if missing:
        raise RuntimeError(
            "Missing secrets: " + ", ".join(missing)
            + f" (looked in Secrets Manager via {SECRET_NAME_VARIABLE}, then in environment variables)"
        )
    return values
