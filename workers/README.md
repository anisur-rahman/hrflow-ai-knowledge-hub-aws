# Lambda workers

Both workers reuse the backend's `app` package (one container image, `workers/Dockerfile`).

| Worker | Trigger | Does |
|---|---|---|
| `ingest_lambda` | S3 `ObjectCreated` → SQS `ingest` queue; API reprocess messages | Extracts digital PDFs and runs classification, summarization, chunking and embeddings. For scanned PDFs it starts async Textract and returns |
| `textract_callback` | Textract → SNS → SQS `textract-results` queue | Collects OCR text, then runs the same pipeline |

Each queue has a dead-letter queue (3 attempts). Both workers return SQS partial batch failures, and both are idempotent: documents are claimed with a row lock and status checks, and chunks are replaced, not appended.
