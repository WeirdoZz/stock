from __future__ import annotations
import chromadb
from chromadb.config import Settings as ChromaSettings
from sentence_transformers import SentenceTransformer
from config.settings import settings

_client: chromadb.PersistentClient | None = None
_collection = None
_embedder: SentenceTransformer | None = None


def _get_client():
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(
            path=settings.chroma_path,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    return _client


def _get_collection():
    global _collection
    if _collection is None:
        _collection = _get_client().get_or_create_collection(
            name="news_headlines",
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def _get_embedder() -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer(settings.embedding_model)
    return _embedder


def embed_articles(articles: list[dict]) -> None:
    """Embed a list of article dicts (id, ticker, headline, published_at, sentiment_label)."""
    if not articles:
        return
    collection = _get_collection()
    embedder = _get_embedder()

    texts = [a["headline"] for a in articles]
    ids = [a["id"] for a in articles]
    metadatas = [
        {
            "ticker": a["ticker"],
            "published_at": str(a["published_at"]),
            "sentiment_label": a.get("sentiment_label", ""),
            "sentiment_score": float(a.get("sentiment_score") or 0.0),
        }
        for a in articles
    ]

    embeddings = embedder.encode(texts, show_progress_bar=False).tolist()
    collection.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)


def search_similar(
    query_headlines: list[str],
    ticker: str,
    n_results: int = 8,
) -> list[dict]:
    """Return past articles semantically similar to query_headlines for the given ticker."""
    collection = _get_collection()
    embedder = _get_embedder()

    # Average-embed the query headlines
    query_text = " | ".join(query_headlines)
    query_vec = embedder.encode([query_text], show_progress_bar=False).tolist()

    results = collection.query(
        query_embeddings=query_vec,
        n_results=min(n_results, max(collection.count(), 1)),
        where={"ticker": ticker},
        include=["documents", "metadatas", "distances"],
    )

    output = []
    if results["ids"] and results["ids"][0]:
        for doc_id, doc, meta, dist in zip(
            results["ids"][0],
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            output.append(
                {
                    "id": doc_id,
                    "headline": doc,
                    "ticker": meta.get("ticker"),
                    "published_at": meta.get("published_at"),
                    "sentiment_label": meta.get("sentiment_label"),
                    "similarity": round(1 - dist, 3),
                }
            )
    return output
