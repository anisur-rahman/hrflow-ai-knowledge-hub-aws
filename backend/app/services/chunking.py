"""Page-aware, overlapping chunks that keep the section heading they belong to."""
from app.services.extraction import PageText

CHUNK_SIZE = 1100
CHUNK_OVERLAP = 160


def chunk_spans(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[tuple[int, int]]:
    """Overlapping windows that prefer to break on whitespace."""
    if size <= overlap or overlap < 0:
        raise ValueError('Invalid chunk parameters')
    spans, start, n = [], 0, len(text)
    while start < n:
        end = min(start + size, n)
        if end < n:
            cut = max(text.rfind(' ', start + size // 2, end), text.rfind('\n', start + size // 2, end))
            if cut > start:
                end = cut
        if text[start:end].strip():
            spans.append((start, end))
        if end >= n:
            break
        next_start = max(end - overlap, start + 1)
        boundary = text.find(' ', next_start, end)
        start = boundary + 1 if boundary != -1 else next_start
    return spans


def split_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    return [text[s:e].strip() for s, e in chunk_spans(text, size, overlap)]


def build_chunks(pages: list[PageText]) -> list[tuple[int, int, str | None, str]]:
    """(page, position, heading, content). A section heading carries over to later pages."""
    pieces, current = [], None
    for page in pages:
        pending = list(page.headings)
        for position, (start, end) in enumerate(chunk_spans(page.text)):
            while pending and pending[0][0] <= start + 120:
                current = pending.pop(0)[1]
            pieces.append((page.number, position, current, page.text[start:end].strip()))
        if pending:
            current = pending[-1][1]
    return pieces
