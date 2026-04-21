from __future__ import annotations
from storage.repository import get_unembedded_articles, mark_articles_embedded
from storage.vector_store import embed_articles


def embed_pending(ticker: str | None = None, batch_size: int = 64) -> int:
    """Embed all articles not yet in ChromaDB. Returns count embedded."""
    articles = get_unembedded_articles(ticker=ticker)
    if not articles:
        return 0

    total = 0
    for i in range(0, len(articles), batch_size):
        batch = articles[i : i + batch_size]
        embed_articles(batch)
        mark_articles_embedded([a["id"] for a in batch])
        total += len(batch)

    return total
