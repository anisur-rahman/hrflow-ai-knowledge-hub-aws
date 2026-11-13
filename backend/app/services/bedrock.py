"""Shared Amazon Bedrock runtime client and Converse helper."""
import json
import logging
import re
import time
from functools import lru_cache

import boto3
from botocore.config import Config

from app.config import settings
from app.observability import log_event


@lru_cache
def client():
    return boto3.client('bedrock-runtime', region_name=settings.aws_region,
                        config=Config(retries={'mode': 'adaptive', 'max_attempts': 6}, connect_timeout=5, read_timeout=60))


def converse_request(system: str, messages: list[dict], max_tokens: int) -> dict:
    """Converse parameters that current Claude models accept.

    - No temperature by default: current Claude models reject sampling parameters with a validation error.
      BEDROCK_TEMPERATURE re-enables it for models that still accept it.
    - max_tokens is a ceiling that includes the model's thinking, so callers leave generous headroom.
    - BEDROCK_EFFORT (optional) passes Claude's output_config.effort through additionalModelRequestFields.
    """
    request = {'modelId': settings.bedrock_chat_model_id, 'system': [{'text': system}], 'messages': messages,
               'inferenceConfig': {'maxTokens': max_tokens}}
    if settings.bedrock_temperature is not None:
        request['inferenceConfig']['temperature'] = settings.bedrock_temperature
    if settings.bedrock_effort:
        request['additionalModelRequestFields'] = {'output_config': {'effort': settings.bedrock_effort}}
    return request


def converse(system: str, messages: list[dict], max_tokens: int, purpose: str) -> str:
    started = time.perf_counter()
    result = client().converse(**converse_request(system, messages, max_tokens))
    usage = result.get('usage', {})
    stop_reason = result.get('stopReason')
    log_event('bedrock.converse', purpose=purpose, duration_ms=round((time.perf_counter() - started) * 1000),
              input_tokens=usage.get('inputTokens'), output_tokens=usage.get('outputTokens'), stop_reason=stop_reason)
    if stop_reason == 'max_tokens':
        log_event('bedrock.truncated', level=logging.WARNING, purpose=purpose, max_tokens=max_tokens)
    # Only text blocks: reasoning (thinking) blocks are never shown to users.
    return ''.join(block.get('text', '') for block in result['output']['message']['content'])


def user_message(text: str) -> dict:
    return {'role': 'user', 'content': [{'text': text}]}


def parse_json_object(raw: str) -> dict:
    """First {...} in a model response, or {} when there is none or it is not valid JSON."""
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    try:
        data = json.loads(match.group(0)) if match else {}
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}
