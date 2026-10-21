"""Read uploaded files from S3.

    name, content = read_file("s3://recruit-uploads-dev/uploads/abc/resume.pdf")

Returns the file name (the last part of the key) and the file's bytes. boto3 is
included in Lambda. The function's role needs s3:GetObject on the bucket.
"""

MAX_BYTES = 25 * 1024 * 1024  

ERROR_HINTS = {
    "NoSuchKey": "there is no file at that key.",
    "NoSuchBucket": "there is no bucket with that name.",
    "AccessDenied": "the function's role cannot read that file. It needs s3:GetObject on the bucket.",
}

_client = None


class S3Error(Exception):
    """The file could not be read from S3."""


def split_s3_url(url):
    """Turn "s3://bucket/some/key.pdf" into ("bucket", "some/key.pdf")."""
    if not isinstance(url, str) or not url.startswith("s3://"):
        raise S3Error(f"Not an S3 URL (expected s3://bucket/key): {url!r}")
    bucket, _, key = url[len("s3://"):].partition("/")
    if not bucket or not key:
        raise S3Error(f"The S3 URL needs a bucket and a key (s3://bucket/key): {url!r}")
    return bucket, key


def read_file(url, *, client=None, max_bytes=MAX_BYTES):
    """Return (file_name, bytes) for the file at an s3:// URL."""
    from botocore.exceptions import ClientError

    bucket, key = split_s3_url(url)
    s3 = client or _get_client()
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        raise S3Error(f"Could not read {url}: {ERROR_HINTS.get(code, code or exc)}") from exc

    size = response["ContentLength"]
    if size > max_bytes:
        raise S3Error(f"{url} is {size} bytes, over the {max_bytes} byte limit")
    return key.rsplit("/", 1)[-1], response["Body"].read()


def _get_client():
    global _client
    if _client is None:
        import boto3

        _client = boto3.client("s3")
    return _client
