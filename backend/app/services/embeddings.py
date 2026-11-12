"""Titan Text Embeddings V2 in Bedrock mode; deterministic hashed vectors in mock mode (NOT semantic)."""
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor

from app.config import settings
from app.models import EMBEDDING_DIMENSIONS
from app.services import bedrock


def embed(text: str) -> list[float]:
    if settings.ai_provider == 'bedrock':
        body = json.dumps({'inputText': text[:8000], 'dimensions': EMBEDDING_DIMENSIONS, 'normalize': True})
        response = bedrock.client().invoke_model(modelId=settings.bedrock_embed_model_id, body=body,
                                                 contentType='application/json', accept='application/json')
        return json.loads(response['body'].read())['embedding']
    return _hashed_embedding(text)


def embed_many(texts: list[str]) -> list[list[float]]:
    if settings.ai_provider != 'bedrock' or len(texts) < 2:
        return [embed(text) for text in texts]
    with ThreadPoolExecutor(max_workers=settings.embed_concurrency) as pool:
        return list(pool.map(embed, texts))


def _hashed_embedding(text: str) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMENSIONS
    for token in re.findall(r'[a-z0-9]+', text.lower()):
        h = int.from_bytes(hashlib.sha256(token.encode()).digest()[:8], 'big')
        vector[h % EMBEDDING_DIMENSIONS] += 1 if h & 1 else -1
    magnitude = sum(x * x for x in vector) ** 0.5 or 1
    return [v / magnitude for v in vector]
