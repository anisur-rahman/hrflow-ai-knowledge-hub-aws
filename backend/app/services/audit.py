from sqlalchemy.orm import Session

from app.models import Audit


def record(db: Session, actor: str, action: str, document_id: str | None = None, **details) -> None:
    """Adds an audit event to the caller's transaction (committed with the change it describes)."""
    db.add(Audit(actor=actor, action=action, document_id=document_id, details=details))
