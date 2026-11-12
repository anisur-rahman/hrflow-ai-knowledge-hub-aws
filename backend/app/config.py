"""Application settings, read from environment variables (and `.env` for local runs)."""
import json
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

DEFAULT_API_KEY = 'local-demo-key-change-me'


def split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(',') if item.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    environment: str = 'local'  # local | dev | prod
    log_level: str = 'INFO'
    aws_region: str = 'us-east-1'

    # Database: a full URL (local) or parts. In AWS the password is injected from
    # Secrets Manager (ECS) or fetched from DB_SECRET_ARN at cold start (Lambda).
    database_url: str = ''
    db_host: str = 'localhost'
    db_port: int = 5432
    db_name: str = 'hrflow'
    db_user: str = 'hrflow'
    db_password: str = ''
    db_secret_arn: str = ''
    hnsw_iterative_scan: bool = True  # needs pgvector >= 0.8

    ai_provider: Literal['mock', 'bedrock'] = 'mock'
    bedrock_chat_model_id: str = ''
    bedrock_embed_model_id: str = 'amazon.titan-embed-text-v2:0'
    embed_concurrency: int = 4
    retrieval_top_k: int = 5
    retrieval_max_distance: float = 0.85

    storage_provider: Literal['local', 's3'] = 'local'
    document_bucket: str = ''
    local_upload_dir: str = '/app/uploads'
    ingestion_queue_url: str = ''  # empty: ingest in-process (local); set: send jobs to SQS
    ocr_provider: Literal['none', 'textract'] = 'none'
    # Async Textract: completion is published to this SNS topic (-> SQS -> textract_callback worker).
    textract_sns_topic_arn: str = ''
    textract_role_arn: str = ''  # role Textract assumes to publish to the topic
    max_upload_bytes: int = 10 * 1024 * 1024
    max_pages: int = 100

    auth_mode: Literal['apikey', 'cognito'] = 'apikey'
    api_key: str = DEFAULT_API_KEY
    api_key_groups: str = 'hr-admin,employee'
    cognito_user_pool_id: str = ''
    cognito_client_id: str = ''
    cognito_domain: str = ''  # hosted UI base URL, e.g. https://x.auth.us-east-1.amazoncognito.com
    admin_group: str = 'hr-admin'
    known_groups: str = 'employee,hr-admin'
    default_document_groups: str = 'employee'

    cors_origins: str = 'http://localhost:5173'

    @model_validator(mode='after')
    def _check_consistency(self):
        problems = []
        if self.environment != 'local' and self.auth_mode != 'cognito':
            problems.append('AUTH_MODE=cognito is required when ENVIRONMENT is not "local"')
        if self.auth_mode == 'cognito' and not (self.cognito_user_pool_id and self.cognito_client_id):
            problems.append('COGNITO_USER_POOL_ID and COGNITO_CLIENT_ID are required for AUTH_MODE=cognito')
        if self.storage_provider == 's3' and not self.document_bucket:
            problems.append('DOCUMENT_BUCKET is required for STORAGE_PROVIDER=s3')
        if self.ocr_provider == 'textract' and not (
                self.storage_provider == 's3' and self.textract_sns_topic_arn and self.textract_role_arn):
            problems.append('OCR_PROVIDER=textract requires STORAGE_PROVIDER=s3, '
                            'TEXTRACT_SNS_TOPIC_ARN and TEXTRACT_ROLE_ARN')
        if self.ai_provider == 'bedrock' and not self.bedrock_chat_model_id:
            problems.append('BEDROCK_CHAT_MODEL_ID is required for AI_PROVIDER=bedrock')
        if problems:
            raise ValueError('; '.join(problems))
        return self

    @property
    def cognito_issuer(self) -> str:
        return f'https://cognito-idp.{self.aws_region}.amazonaws.com/{self.cognito_user_pool_id}'

    def sqlalchemy_url(self) -> str | URL:
        if self.database_url:
            return self.database_url
        username, password = self.db_user, self.db_password
        if not password and self.db_secret_arn:
            username, password = self._credentials_from_secret()
        return URL.create('postgresql+psycopg', username=username, password=password,
                          host=self.db_host, port=self.db_port, database=self.db_name)

    def _credentials_from_secret(self) -> tuple[str, str]:
        import boto3

        secret = boto3.client('secretsmanager', region_name=self.aws_region).get_secret_value(SecretId=self.db_secret_arn)
        data = json.loads(secret['SecretString'])
        return data.get('username', self.db_user), data['password']


settings = Settings()
