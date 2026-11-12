"""pgvector storage and authorized similarity search."""
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Chunk, Document
from app.security import Principal, retrievable_documents


def replace_chunks(db: Session, document_id: str, pieces: list[tuple[int, int, str | None, str]],
                   vectors: list[list[float]]) -> None:
    """Idempotent: re-processing a document replaces its chunks inside the caller's transaction."""
    db.execute(delete(Chunk).where(Chunk.document_id == document_id))
    db.add_all(Chunk(document_id=document_id, page=page, position=position, heading=heading, content=content,
                     embedding=vector)
               for (page, position, heading, content), vector in zip(pieces, vectors, strict=True))


def search(db: Session, vector: list[float], principal: Principal) -> list[dict]:
    if settings.hnsw_iterative_scan:  # keep filtered HNSW searches from returning too few rows (pgvector >= 0.8)
        db.execute(text("SET LOCAL hnsw.iterative_scan = 'relaxed_order'"))
    distance = Chunk.embedding.cosine_distance(vector).label('distance')
    stmt = (select(Chunk.document_id, Chunk.page, Chunk.heading, Chunk.content, Document.title,
                   Document.version_label, distance)
            .join(Document, Document.id == Chunk.document_id)
            .where(retrievable_documents(principal))
            .order_by(distance).limit(settings.retrieval_top_k))
    rows = sorted(db.execute(stmt).all(), key=lambda r: r.distance)
    return [{'document_id': r.document_id, 'title': r.title, 'version': r.version_label, 'page': r.page,
             'heading': r.heading, 'content': r.content, 'distance': float(r.distance)}
            for r in rows if r.distance is not None and r.distance < settings.retrieval_max_distance]
