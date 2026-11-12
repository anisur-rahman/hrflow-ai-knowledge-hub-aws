# One Lambda container image for both workers (build context: repository root).
# Terraform selects the handler per function:
#   workers.ingest_lambda.handler.handler | workers.textract_callback.handler.handler
FROM public.ecr.aws/lambda/python:3.12
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ${LAMBDA_TASK_ROOT}/app
COPY workers ${LAMBDA_TASK_ROOT}/workers
CMD ["workers.ingest_lambda.handler.handler"]
