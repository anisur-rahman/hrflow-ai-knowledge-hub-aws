from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import new_id

EMBEDDING_DIMENSIONS = 1024


class Chunk(Base):
    """A searchable section of a document. Version and access control come from the parent
    document via a join, so changing them never leaves stale copies on chunks."""
    __tablename__ = 'chunks'
    __table_args__ = (UniqueConstraint('document_id', 'page', 'position'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey('documents.id', ondelete='CASCADE'), index=True)
    page: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer)
    heading: Mapped[str | None] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
