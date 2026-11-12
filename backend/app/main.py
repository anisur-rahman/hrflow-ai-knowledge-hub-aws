import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api import admin, chat, documents
from app.config import DEFAULT_API_KEY, settings, split_csv
from app.db import get_db
from app.observability import configure_logging, log_event, request_id_var
from app.security import Principal, current_principal
from app.services.classification import CATEGORIES, UNCATEGORIZED

configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auth_mode == 'apikey' and settings.api_key == DEFAULT_API_KEY:
        log_event('config.warning', level=logging.WARNING, detail='Using the default local API key')
    yield


local = settings.environment == 'local'
app = FastAPI(title='HRFlow AI Knowledge Hub', version='2.1.0', lifespan=lifespan,
              docs_url='/docs' if local else None, redoc_url=None, openapi_url='/openapi.json' if local else None)
app.add_middleware(CORSMiddleware, allow_origins=split_csv(settings.cors_origins),
                   allow_methods=['GET', 'POST', 'PATCH', 'DELETE'],
                   allow_headers=['Authorization', 'Content-Type', 'X-API-Key', 'X-Request-ID'])
app.include_router(documents.router)
app.include_router(admin.router)
app.include_router(chat.router)


@app.middleware('http')
async def request_context(request: Request, call_next):
    request_id = request.headers.get('x-request-id') or uuid.uuid4().hex
    request.state.request_id = request_id
    token = request_id_var.set(request_id)
    started, status = time.perf_counter(), 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers['X-Request-ID'] = request_id
        return response
    finally:
        if not request.url.path.startswith('/health'):
            log_event('http.request', method=request.method, path=request.url.path, status=status,
                      duration_ms=round((time.perf_counter() - started) * 1000))
        request_id_var.reset(token)


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    log_event('http.unhandled_error', level=logging.ERROR, exc_info=(type(exc), exc, exc.__traceback__),
              path=request.url.path)
    return JSONResponse({'detail': 'Internal server error', 'request_id': getattr(request.state, 'request_id', None)},
                        status_code=500)


@app.get('/health', tags=['system'])
def health():
    return {'status': 'ok'}


@app.get('/health/ready', tags=['system'])
def ready(db: Session = Depends(get_db)):
    db.execute(text('SELECT 1'))
    return {'status': 'ready'}


@app.get('/api/config', tags=['system'])
def public_config():
    """Public settings the SPA needs before sign-in."""
    cognito = None
    if settings.auth_mode == 'cognito':
        cognito = {'authority': settings.cognito_issuer, 'client_id': settings.cognito_client_id,
                   'domain': settings.cognito_domain}
    return {'auth_mode': settings.auth_mode, 'cognito': cognito, 'ai_provider': settings.ai_provider,
            'storage_provider': settings.storage_provider, 'max_upload_bytes': settings.max_upload_bytes,
            'admin_group': settings.admin_group, 'groups': split_csv(settings.known_groups),
            'default_groups': split_csv(settings.default_document_groups),
            'categories': [*CATEGORIES, UNCATEGORIZED]}


@app.get('/api/me', tags=['system'])
def me(principal: Principal = Depends(current_principal)):
    return {'username': principal.username, 'groups': sorted(principal.groups), 'is_admin': principal.is_admin}
