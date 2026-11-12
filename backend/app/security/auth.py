"""Authentication and authorization.

AWS: API Gateway's JWT authorizer rejects bad tokens at the edge, and the API verifies the
Cognito access token again (signature, issuer, expiry, client id) so it is never exposed
without checks. Local: a single API key with configurable groups."""
import hmac
from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings, split_csv

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    subject: str
    username: str
    groups: frozenset[str]

    @property
    def is_admin(self) -> bool:
        return settings.admin_group in self.groups


class InvalidToken(Exception):
    pass


@lru_cache
def _jwks_client() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f'{settings.cognito_issuer}/.well-known/jwks.json', cache_keys=True, lifespan=3600)


def verify_cognito_access_token(token: str) -> Principal:
    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(token, signing_key.key, algorithms=['RS256'], issuer=settings.cognito_issuer,
                            options={'require': ['exp', 'iat', 'iss', 'sub', 'token_use'], 'verify_aud': False},
                            leeway=30)
    except jwt.PyJWTError as exc:
        raise InvalidToken(str(exc)) from exc
    # Cognito access tokens carry client_id instead of aud.
    if claims.get('token_use') != 'access':
        raise InvalidToken('An access token is required')
    if claims.get('client_id') != settings.cognito_client_id:
        raise InvalidToken('Token was issued for a different client')
    groups = claims.get('cognito:groups') or []
    return Principal(subject=claims['sub'], username=claims.get('username', claims['sub']), groups=frozenset(groups))


def current_principal(x_api_key: str | None = Header(default=None),
                      credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> Principal:
    if settings.auth_mode == 'apikey':
        if not x_api_key or not hmac.compare_digest(x_api_key.encode(), settings.api_key.encode()):
            raise HTTPException(401, 'Invalid API key')
        return Principal('local-api-key', 'local-demo', frozenset(split_csv(settings.api_key_groups)))
    if credentials is None or credentials.scheme.lower() != 'bearer':
        raise HTTPException(401, 'Missing bearer token', headers={'WWW-Authenticate': 'Bearer'})
    try:
        return verify_cognito_access_token(credentials.credentials)
    except InvalidToken:
        raise HTTPException(401, 'Invalid or expired token', headers={'WWW-Authenticate': 'Bearer'}) from None


def require_admin(principal: Principal = Depends(current_principal)) -> Principal:
    if not principal.is_admin:
        raise HTTPException(403, f'Requires the {settings.admin_group} group')
    return principal
