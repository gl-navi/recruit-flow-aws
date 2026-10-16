# Worker Lambda image. Build from the repo root:
#   docker buildx build --platform linux/amd64 --provenance=false -f src/worker/Dockerfile -t <tag> --load .
FROM public.ecr.aws/lambda/python:3.14

# libmagic is the system library behind python-magic (the file type check).
# The Lambda base image does not include it, which is why the worker is a container.
RUN microdnf install -y file-libs && microdnf clean all

COPY src/worker/requirements.txt ${LAMBDA_TASK_ROOT}/requirements.txt
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

COPY src/worker/ ${LAMBDA_TASK_ROOT}/
COPY src/shared/ ${LAMBDA_TASK_ROOT}/shared/

CMD ["lambda_function.lambda_handler"]
