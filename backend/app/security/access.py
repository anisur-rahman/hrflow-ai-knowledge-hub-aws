"""Document-level authorization, expressed as SQL so it is applied before any text reaches the LLM."""
from sqlalchemy import true

from app.models import Document, Status
from app.security.auth import Principal


def visible_documents(principal: Principal):
    """Admins manage every document; everyone else sees published documents shared with one of their groups."""
    if principal.is_admin:
        return true()
    return (Document.status == Status.PUBLISHED) & Document.allowed_groups.overlap(sorted(principal.groups))


def retrievable_documents(principal: Principal):
    """What the assistant may quote: published only, even for admins, and only the caller's groups."""
    condition = Document.status == Status.PUBLISHED
    if not principal.is_admin:
        condition = condition & Document.allowed_groups.overlap(sorted(principal.groups))
    return condition
