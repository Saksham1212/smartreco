"""ChromaDB vector store logic. All embeddings are generated via the Mesh API
(OpenAI-SDK compatible). ChromaDB itself runs in-process with disk persistence.
"""
import asyncio
import logging
from typing import Optional

import chromadb
from openai import AsyncOpenAI

from config import settings
from observability import traceable

logger = logging.getLogger("smartreco.vector_store")

_mesh_client = AsyncOpenAI(base_url=settings.MESH_BASE_URL, api_key=settings.MESH_API_KEY)

_chroma_client: Optional[chromadb.ClientAPI] = None
_collection = None

# In-memory retry queue for products whose embedding/upsert failed.
failed_vector_writes: set[int] = set()


def init_vector_store():
    """Initialize the persistent ChromaDB client and collection. Call once at startup."""
    global _chroma_client, _collection
    _chroma_client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_PATH)
    _collection = _chroma_client.get_or_create_collection(
        name=settings.CHROMA_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    logger.info("ChromaDB collection '%s' ready (%d items)", settings.CHROMA_COLLECTION_NAME, _collection.count())
    return _collection


def get_collection():
    if _collection is None:
        return init_vector_store()
    return _collection


@traceable(name="mesh_embedding", run_type="embedding")
async def get_embedding(text: str) -> list[float]:
    """Get an embedding vector for a piece of text via the Mesh API."""
    response = await _mesh_client.embeddings.create(model=settings.EMBEDDING_MODEL, input=text)
    return response.data[0].embedding


def build_product_document(product) -> str:
    """Combine product fields into one rich text string for embedding."""
    parts = [
        f"Title: {product.title}",
        f"Category: {product.category}",
        f"Difficulty: {product.difficulty_level}",
        f"Instructor: {product.instructor_name}",
        f"Duration: {product.duration_hours} hours",
        f"Tags: {product.tags}",
        f"Description: {product.description}",
    ]
    return "\n".join(parts)


async def upsert_product(product) -> bool:
    """Dual-write a product into ChromaDB. Returns True on success, False on failure
    (in which case the product id is queued for retry)."""
    collection = get_collection()
    document = build_product_document(product)
    try:
        embedding = await get_embedding(document)
        await asyncio.to_thread(
            collection.upsert,
            ids=[str(product.id)],
            embeddings=[embedding],
            documents=[document],
            metadatas=[
                {
                    "product_id": product.id,
                    "title": product.title,
                    "category": product.category,
                    "difficulty_level": product.difficulty_level,
                    "price": product.price,
                    "tags": product.tags or "",
                    "is_active": bool(product.is_active),
                }
            ],
        )
        failed_vector_writes.discard(product.id)
        return True
    except Exception:
        logger.exception("Failed to upsert product %s into ChromaDB; queued for retry", product.id)
        failed_vector_writes.add(product.id)
        return False


async def delete_product(product_id: int) -> bool:
    collection = get_collection()
    try:
        await asyncio.to_thread(collection.delete, ids=[str(product_id)])
        failed_vector_writes.discard(product_id)
        return True
    except Exception:
        logger.exception("Failed to delete product %s from ChromaDB", product_id)
        return False


@traceable(name="chroma_semantic_search", run_type="retriever")
async def semantic_search(
    query: str,
    n_results: int = 15,
    where: Optional[dict] = None,
) -> list[dict]:
    """Run a semantic search against the product collection.

    Returns a list of dicts: {id, score (cosine similarity, higher=better), metadata, document}
    Returns an empty list if the collection is empty or the query fails.
    """
    collection = get_collection()
    try:
        if collection.count() == 0:
            return []
    except Exception:
        logger.exception("Failed to read ChromaDB collection count")
        return []

    try:
        query_embedding = await get_embedding(query)
        kwargs = {
            "query_embeddings": [query_embedding],
            "n_results": min(n_results, max(collection.count(), 1)),
        }
        if where:
            kwargs["where"] = where
        results = await asyncio.to_thread(collection.query, **kwargs)
    except Exception:
        logger.exception("Semantic search failed for query=%r", query)
        return []

    output = []
    ids = results.get("ids", [[]])[0]
    distances = results.get("distances", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    documents = results.get("documents", [[]])[0]
    for i, doc_id in enumerate(ids):
        distance = distances[i] if i < len(distances) else 1.0
        # Cosine distance -> similarity score
        score = 1.0 - distance
        output.append(
            {
                "id": doc_id,
                "score": score,
                "metadata": metadatas[i] if i < len(metadatas) else {},
                "document": documents[i] if i < len(documents) else "",
            }
        )
    return output


async def retry_failed_writes(db_session_factory, product_model):
    """Periodically retry vector writes that failed earlier. Called by the scheduler."""
    if not failed_vector_writes:
        return
    ids_to_retry = list(failed_vector_writes)
    async with db_session_factory() as db:
        from sqlalchemy import select

        result = await db.execute(select(product_model).where(product_model.id.in_(ids_to_retry)))
        products = result.scalars().all()
        for product in products:
            await upsert_product(product)
