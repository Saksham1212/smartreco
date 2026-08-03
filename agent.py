"""The recommendation agent pipeline — the heart of SmartReco.

Implemented as an explicit LangGraph state machine so the agent's reasoning is
a real, inspectable workflow rather than a single opaque function:

    analyze_behavior -> build_query -> retrieve -> evaluate_quality
        -> (retry retrieve with relaxed filters, up to 2x) -> rerank
        -> generate -> store

Each node is a small, traceable step. `evaluate_quality` decides whether the
retrieval is good enough (>=3 relevant, not-already-seen candidates) or
whether the graph should loop back into `retrieve` with broadened filters.
`rerank` re-scores the survivors (semantic score + category-match + recency)
and diversifies the final list before the LLM ever sees it.

When LANGCHAIN_TRACING_V2 is set (see config.py), every node shows up as a
step in a single LangSmith trace per pipeline run.
"""
import datetime
import json
import logging
import re
import time
from collections import Counter
from typing import Any, Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from openai import AsyncOpenAI
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

import vector_store
from config import settings
from models import Event, Product, Recommendation, User
from observability import traceable

logger = logging.getLogger("smartreco.agent")

_mesh_chat_client = AsyncOpenAI(base_url=settings.MESH_BASE_URL, api_key=settings.MESH_API_KEY)

# Concurrency guard: user_ids for which a pipeline run is currently in-flight.
_running_users: set[int] = set()

FALLBACK_NARRATIVE = (
    "We're putting together your personalized recommendations right now, but our "
    "recommendation engine is temporarily unavailable. Please check back again shortly — "
    "in the meantime, feel free to keep browsing the catalog."
)

MAX_RETRIEVAL_ATTEMPTS = 2


# ---------------------------------------------------------------------------
# Trigger logic (unchanged — runs before the graph, cheap and synchronous-ish)
# ---------------------------------------------------------------------------

async def should_run_agent(db, user_id: int) -> bool:
    total_events = (
        await db.execute(select(func.count(Event.id)).where(Event.user_id == user_id))
    ).scalar_one()

    rec = (
        await db.execute(select(Recommendation).where(Recommendation.user_id == user_id))
    ).scalar_one_or_none()

    if rec is None:
        return total_events >= 5

    events_since = (
        await db.execute(
            select(func.count(Event.id)).where(
                Event.user_id == user_id, Event.created_at > rec.updated_at
            )
        )
    ).scalar_one()

    if events_since >= settings.AGENT_TRIGGER_THRESHOLD:
        return True

    age = datetime.datetime.utcnow() - rec.updated_at
    if age > datetime.timedelta(hours=2) and events_since >= 3:
        return True

    return False


async def maybe_run_agent(user_id: int):
    """Entry point called from a FastAPI BackgroundTask. Opens its own DB session
    since it runs outside the request lifecycle."""
    from database import AsyncSessionLocal

    if user_id in _running_users:
        logger.info("Agent already running for user %s, skipping", user_id)
        return

    try:
        async with AsyncSessionLocal() as db:
            if not await should_run_agent(db, user_id):
                return
    except Exception:
        logger.exception("Failed to evaluate trigger for user %s", user_id)
        return

    _running_users.add(user_id)
    try:
        async with AsyncSessionLocal() as db:
            await _run_pipeline(db, user_id)
    except Exception:
        logger.exception("Agent pipeline crashed for user %s", user_id)
    finally:
        _running_users.discard(user_id)


# ---------------------------------------------------------------------------
# Behavioral profile
# ---------------------------------------------------------------------------

def _parse_metadata(event: Event) -> dict:
    if not event.metadata_json:
        return {}
    try:
        return json.loads(event.metadata_json)
    except (json.JSONDecodeError, TypeError):
        return {}


def build_behavioral_profile(events: list[Event], total_events_count: int) -> dict:
    category_counts: Counter = Counter()
    difficulty_counts: Counter = Counter()
    product_view_counts: Counter = Counter()
    product_time_spent: Counter = Counter()
    deep_scroll_product_ids: set[int] = set()
    add_to_cart_product_ids: set[int] = set()
    search_queries: list[str] = []
    products_seen: dict[int, Product] = {}
    signal_event_count = 0

    for event in events:
        meta = _parse_metadata(event)

        if event.event_type == "product_view" and event.product_id:
            product_view_counts[event.product_id] += 1
            signal_event_count += 1
            if event.product:
                products_seen[event.product_id] = event.product
                category_counts[event.product.category] += 1
                difficulty_counts[event.product.difficulty_level] += 1

        elif event.event_type == "search" and event.search_query:
            q = event.search_query.strip()
            if q and q not in search_queries:
                search_queries.append(q)
            signal_event_count += 1

        elif event.event_type == "search_result_click" and event.product_id:
            product_view_counts[event.product_id] += 1
            signal_event_count += 1
            if event.product:
                products_seen[event.product_id] = event.product

        elif event.event_type == "scroll_depth" and event.product_id:
            depth = meta.get("scroll_depth_percent")
            if isinstance(depth, (int, float)) and depth > 70:
                deep_scroll_product_ids.add(event.product_id)
            signal_event_count += 1

        elif event.event_type == "time_on_page" and event.product_id:
            seconds = meta.get("time_spent_seconds")
            if isinstance(seconds, (int, float)):
                product_time_spent[event.product_id] += seconds
            signal_event_count += 1

        elif event.event_type == "add_to_cart" and event.product_id:
            add_to_cart_product_ids.add(event.product_id)
            signal_event_count += 1
            if event.product:
                products_seen[event.product_id] = event.product
                category_counts[event.product.category] += 2
                difficulty_counts[event.product.difficulty_level] += 2

    most_viewed_product_id = product_view_counts.most_common(1)[0][0] if product_view_counts else None

    if total_events_count < 10:
        activity_level = "low"
    elif total_events_count < 30:
        activity_level = "medium"
    else:
        activity_level = "high"

    engaged_difficulty_levels = {level for level, count in difficulty_counts.items() if count > 0}

    return {
        "category_counts": category_counts,
        "difficulty_counts": difficulty_counts,
        "engaged_difficulty_levels": engaged_difficulty_levels,
        "product_view_counts": product_view_counts,
        "product_time_spent": product_time_spent,
        "deep_scroll_product_ids": deep_scroll_product_ids,
        "add_to_cart_product_ids": add_to_cart_product_ids,
        "search_queries": search_queries,
        "products_seen": products_seen,
        "most_viewed_product_id": most_viewed_product_id,
        "activity_level": activity_level,
        "total_events_count": total_events_count,
        "signal_event_count": signal_event_count,
    }


def build_behavioral_summary(profile: dict, user: User) -> str:
    parts = []

    top_categories = [c for c, _ in profile["category_counts"].most_common(3)]
    if top_categories:
        parts.append(f"shows clear interest in {', '.join(top_categories)}")

    if profile["search_queries"]:
        queries_preview = ", ".join(f'"{q}"' for q in profile["search_queries"][:5])
        parts.append(f"has searched for {queries_preview}")

    if profile["engaged_difficulty_levels"]:
        levels = ", ".join(sorted(profile["engaged_difficulty_levels"]))
        parts.append(f"engages mostly with {levels}-level content")

    most_viewed = profile["most_viewed_product_id"]
    products_seen = profile["products_seen"]
    if most_viewed and most_viewed in products_seen:
        parts.append(f"has repeatedly viewed '{products_seen[most_viewed].title}'")

    if profile["deep_scroll_product_ids"]:
        titles = [
            products_seen[pid].title for pid in profile["deep_scroll_product_ids"] if pid in products_seen
        ]
        if titles:
            parts.append(f"scrolled deeply through {', '.join(titles[:3])}, signaling strong interest")

    if profile["add_to_cart_product_ids"]:
        titles = [
            products_seen[pid].title for pid in profile["add_to_cart_product_ids"] if pid in products_seen
        ]
        if titles:
            parts.append(f"added {', '.join(titles[:3])} to their cart")

    parts.append(f"overall activity level is {profile['activity_level']}")

    if not top_categories and not profile["search_queries"] and not products_seen:
        return (
            f"{user.full_name} has been browsing the site but hasn't yet engaged with specific "
            f"products or searches. Activity level is {profile['activity_level']}."
        )

    return f"{user.full_name} " + "; ".join(parts) + "."


def build_search_query(profile: dict) -> str:
    tokens: list[str] = []

    if profile["engaged_difficulty_levels"] and "beginner" not in profile["engaged_difficulty_levels"]:
        tokens.append(sorted(profile["engaged_difficulty_levels"])[0])

    top_categories = [c for c, _ in profile["category_counts"].most_common(2)]
    tokens.extend(top_categories)

    tokens.extend(profile["search_queries"][:3])

    products_seen = profile["products_seen"]
    most_viewed = profile["most_viewed_product_id"]
    if most_viewed and most_viewed in products_seen:
        tokens.append(products_seen[most_viewed].title)

    tokens.append("practical hands-on projects")

    query = " ".join(tokens).strip()
    return query if query else "popular trending courses"


def _product_to_candidate(p: Product) -> dict:
    return {
        "id": p.id,
        "title": p.title,
        "category": p.category,
        "difficulty_level": p.difficulty_level,
        "description": p.description,
        "price": p.price,
        "thumbnail_url": p.thumbnail_url,
    }


# ---------------------------------------------------------------------------
# SQL fallback for cold-start / signal-less users
# ---------------------------------------------------------------------------

async def get_popular_products(db, limit: int = 5) -> list[Product]:
    result = await db.execute(
        select(Product.id, func.count(Event.id).label("view_count"))
        .join(Event, Event.product_id == Product.id)
        .where(Event.event_type == "product_view", Product.is_active.is_(True))
        .group_by(Product.id)
        .order_by(func.count(Event.id).desc())
        .limit(limit)
    )
    rows = result.all()
    if not rows:
        fallback = await db.execute(
            select(Product).where(Product.is_active.is_(True)).order_by(Product.created_at.desc()).limit(limit)
        )
        return list(fallback.scalars().all())

    ids = [row[0] for row in rows]
    products_result = await db.execute(select(Product).where(Product.id.in_(ids)))
    products_by_id = {p.id: p for p in products_result.scalars().all()}
    return [products_by_id[i] for i in ids if i in products_by_id]


# ---------------------------------------------------------------------------
# LLM narrative generation
# ---------------------------------------------------------------------------

JSON_BLOCK_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


@traceable(name="generate_recommendation_narrative", run_type="llm")
async def generate_narrative(user: User, behavioral_summary: str, candidates: list[dict]) -> tuple[str, list[int]]:
    """Call the Mesh chat completion API. Returns (narrative_text, ordered_product_ids)."""
    first_name = user.full_name.split(" ")[0] if user.full_name else "there"

    candidate_lines = []
    for c in candidates:
        candidate_lines.append(
            f"- id={c['id']} | title=\"{c['title']}\" | category={c['category']} | "
            f"difficulty={c['difficulty_level']} | description={c['description'][:220]}"
        )
    candidate_block = "\n".join(candidate_lines)

    system_prompt = (
        "You are SmartReco's personalized learning advisor, an AI agent that studies a learner's "
        "real browsing behavior and recommends the most relevant courses from a retrieved candidate "
        "list. You write warm, intelligent, and direct recommendations — never generic, never "
        "sycophantic, never sales-y. You always ground your reasoning in the specific behavior "
        "described to you."
    )

    user_prompt = (
        f"Learner name: {first_name}\n\n"
        f"Behavioral summary: {behavioral_summary}\n\n"
        f"Candidate courses retrieved from the catalog (choose only from these):\n{candidate_block}\n\n"
        "Write a 3-4 sentence first-person-to-the-learner recommendation narrative. Address "
        f"{first_name} by name, reference specific things from their browsing behavior described "
        "above, explain why the courses you pick fit where they are in their learning journey right "
        "now, and end with a motivating call to action.\n\n"
        "After the narrative, output a fenced json code block with the final ranked list of 2 to 5 "
        "product ids chosen from the candidates above, best fit first, in exactly this shape:\n"
        "```json\n{\"product_ids\": [id1, id2, id3]}\n```"
    )

    response = await _mesh_chat_client.chat.completions.create(
        model=settings.CHAT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
        max_tokens=600,
    )
    content = response.choices[0].message.content or ""

    product_ids: list[int] = []
    match = JSON_BLOCK_RE.search(content)
    if match:
        try:
            parsed = json.loads(match.group(1))
            raw_ids = parsed.get("product_ids", [])
            candidate_ids = {c["id"] for c in candidates}
            product_ids = [int(pid) for pid in raw_ids if int(pid) in candidate_ids]
        except (json.JSONDecodeError, ValueError, TypeError):
            logger.warning("Failed to parse product_ids JSON block from LLM output")

    narrative = JSON_BLOCK_RE.sub("", content).strip()

    if not product_ids:
        product_ids = [c["id"] for c in candidates[:5]]
    if not narrative:
        narrative = (
            f"Hi {first_name}, based on what you've been exploring, here are a few courses "
            "worth checking out next."
        )

    return narrative, product_ids[:5]


# ---------------------------------------------------------------------------
# LangGraph state machine
# ---------------------------------------------------------------------------

class AgentState(TypedDict, total=False):
    db: Any
    user: Any
    user_id: int
    start_time: float
    total_events_count: int
    profile: dict
    behavioral_summary: str
    query_text: Optional[str]
    where_filter: Optional[dict]
    retrieval_attempts: int
    raw_results: list
    candidate_ids: list[int]
    retrieval_scores: dict
    quality_ok: bool
    candidates: list[dict]
    narrative: Optional[str]
    product_ids: list[int]
    model_used: Optional[str]


@traceable(name="node_analyze_behavior", run_type="chain")
async def node_analyze_behavior(state: AgentState) -> dict:
    db = state["db"]
    user = state["user"]
    user_id = state["user_id"]

    total_events_count = (
        await db.execute(select(func.count(Event.id)).where(Event.user_id == user_id))
    ).scalar_one()

    if total_events_count == 0:
        return {"total_events_count": 0}

    events_result = await db.execute(
        select(Event)
        .options(selectinload(Event.product))
        .where(Event.user_id == user_id)
        .order_by(Event.created_at.desc())
        .limit(60)
    )
    events = list(events_result.scalars().all())

    profile = build_behavioral_profile(events, total_events_count)
    behavioral_summary = build_behavioral_summary(profile, user)

    return {
        "total_events_count": total_events_count,
        "profile": profile,
        "behavioral_summary": behavioral_summary,
    }


def route_after_analyze(state: AgentState) -> str:
    return "end" if state.get("total_events_count", 0) == 0 else "continue"


@traceable(name="node_build_query", run_type="chain")
async def node_build_query(state: AgentState) -> dict:
    profile = state["profile"]

    if profile["signal_event_count"] == 0:
        # No product/search signal at all -> skip semantic retrieval, use popular fallback.
        return {"query_text": None, "where_filter": None, "retrieval_attempts": 0}

    query_text = build_search_query(profile)

    engaged = profile["engaged_difficulty_levels"]
    if engaged and "beginner" not in engaged:
        where_filter = {"$and": [{"is_active": True}, {"difficulty_level": {"$in": sorted(engaged)}}]}
    else:
        where_filter = {"is_active": True}

    return {"query_text": query_text, "where_filter": where_filter, "retrieval_attempts": 0}


@traceable(name="node_retrieve", run_type="retriever")
async def node_retrieve(state: AgentState) -> dict:
    if state.get("query_text") is None:
        popular = await get_popular_products(state["db"], limit=5)
        candidates = [_product_to_candidate(p) for p in popular]
        return {
            "candidates": candidates,
            "retrieval_scores": {},
            "quality_ok": True,
        }

    results = await vector_store.semantic_search(
        state["query_text"], n_results=15, where=state.get("where_filter")
    )
    attempts = state.get("retrieval_attempts", 0) + 1
    return {"raw_results": results, "retrieval_attempts": attempts}


@traceable(name="node_evaluate_quality", run_type="chain")
async def node_evaluate_quality(state: AgentState) -> dict:
    if state.get("candidates"):
        # Already resolved via the popular-products cold-start path.
        return {"quality_ok": True}

    profile = state["profile"]
    results = state.get("raw_results") or []
    already_seen_heavily = {pid for pid, count in profile["product_view_counts"].items() if count >= 3}

    ordered_ids: list[int] = []
    retrieval_scores = dict(state.get("retrieval_scores") or {})
    for r in results:
        pid = r["metadata"].get("product_id")
        if pid is None or pid in already_seen_heavily:
            continue
        if pid not in ordered_ids:
            ordered_ids.append(pid)
            retrieval_scores[str(pid)] = r["score"]

    attempts = state.get("retrieval_attempts", 0)
    quality_ok = len(ordered_ids) >= 3 or attempts >= MAX_RETRIEVAL_ATTEMPTS

    updates: dict = {
        "candidate_ids": ordered_ids[:8],
        "retrieval_scores": retrieval_scores,
        "quality_ok": quality_ok,
    }
    if not quality_ok:
        # Refine: drop the difficulty filter and retry retrieval once more.
        updates["where_filter"] = {"is_active": True}
    return updates


def route_after_evaluate(state: AgentState) -> str:
    return "proceed" if state.get("quality_ok") else "retry"


@traceable(name="node_rerank", run_type="chain")
async def node_rerank(state: AgentState) -> dict:
    if state.get("candidates"):
        return {}  # cold-start popular-products path already produced the final list

    candidate_ids = state.get("candidate_ids") or []
    if not candidate_ids:
        popular = await get_popular_products(state["db"], limit=5)
        return {"candidates": [_product_to_candidate(p) for p in popular]}

    db = state["db"]
    profile = state["profile"]
    retrieval_scores = state.get("retrieval_scores") or {}

    products_result = await db.execute(select(Product).where(Product.id.in_(candidate_ids)))
    products_by_id = {p.id: p for p in products_result.scalars().all()}

    top_categories = {c for c, _ in profile["category_counts"].most_common(2)}
    now = datetime.datetime.utcnow()

    scored: list[tuple[float, Product]] = []
    for pid in candidate_ids:
        p = products_by_id.get(pid)
        if p is None:
            continue
        base_score = retrieval_scores.get(str(pid), 0.0)
        category_boost = 0.08 if p.category in top_categories else 0.0
        age_days = max((now - p.created_at).days, 0)
        recency_boost = max(0.0, 0.04 - age_days * 0.0005)
        scored.append((base_score + category_boost + recency_boost, p))

    scored.sort(key=lambda t: t[0], reverse=True)

    # Diversify: cap 2 per category so the final list isn't 5 near-duplicates.
    diversified: list[Product] = []
    seen_category_counts: Counter = Counter()
    for _score, p in scored:
        if seen_category_counts[p.category] >= 2:
            continue
        diversified.append(p)
        seen_category_counts[p.category] += 1
        if len(diversified) >= 5:
            break

    if len(diversified) < min(5, len(scored)):
        for _score, p in scored:
            if p not in diversified:
                diversified.append(p)
            if len(diversified) >= 5:
                break

    return {"candidates": [_product_to_candidate(p) for p in diversified]}


@traceable(name="node_generate", run_type="chain")
async def node_generate(state: AgentState) -> dict:
    candidates = state.get("candidates") or []
    if not candidates:
        return {"narrative": None, "product_ids": [], "model_used": None}

    user = state["user"]
    behavioral_summary = state.get("behavioral_summary") or (
        f"{user.full_name} is a new learner exploring the catalog."
    )

    try:
        narrative, ranked_ids = await generate_narrative(user, behavioral_summary, candidates)
        return {"narrative": narrative, "product_ids": ranked_ids, "model_used": settings.CHAT_MODEL}
    except Exception:
        logger.exception("LLM call failed while generating recommendation for user %s", state["user_id"])
        return {
            "narrative": FALLBACK_NARRATIVE,
            "product_ids": [c["id"] for c in candidates[:5]],
            "model_used": "fallback",
        }


@traceable(name="node_store", run_type="chain")
async def node_store(state: AgentState) -> dict:
    if not state.get("candidates") or not state.get("product_ids"):
        logger.info("No candidates for user %s; skipping recommendation write", state["user_id"])
        return {}

    db = state["db"]
    user_id = state["user_id"]
    duration_ms = int((time.monotonic() - state["start_time"]) * 1000)

    existing = (
        await db.execute(select(Recommendation).where(Recommendation.user_id == user_id))
    ).scalar_one_or_none()

    if existing is None:
        existing = Recommendation(user_id=user_id)
        db.add(existing)

    existing.narrative = state["narrative"]
    existing.product_ids_json = json.dumps(state["product_ids"])
    existing.behavioral_summary = state.get("behavioral_summary")
    existing.retrieval_scores_json = json.dumps(state.get("retrieval_scores") or {})
    existing.events_count_at_generation = state.get("total_events_count", 0)
    existing.model_used = state.get("model_used")
    existing.generation_duration_ms = duration_ms
    existing.updated_at = datetime.datetime.utcnow()

    await db.commit()
    logger.info(
        "Generated recommendation for user %s (%d products, %dms)",
        user_id,
        len(state["product_ids"]),
        duration_ms,
    )
    return {}


def _build_agent_graph():
    graph = StateGraph(AgentState)
    graph.add_node("analyze_behavior", node_analyze_behavior)
    graph.add_node("build_query", node_build_query)
    graph.add_node("retrieve", node_retrieve)
    graph.add_node("evaluate_quality", node_evaluate_quality)
    graph.add_node("rerank", node_rerank)
    graph.add_node("generate", node_generate)
    graph.add_node("store", node_store)

    graph.add_edge(START, "analyze_behavior")
    graph.add_conditional_edges(
        "analyze_behavior", route_after_analyze, {"continue": "build_query", "end": END}
    )
    graph.add_edge("build_query", "retrieve")
    graph.add_edge("retrieve", "evaluate_quality")
    graph.add_conditional_edges(
        "evaluate_quality", route_after_evaluate, {"retry": "retrieve", "proceed": "rerank"}
    )
    graph.add_edge("rerank", "generate")
    graph.add_edge("generate", "store")
    graph.add_edge("store", END)

    return graph.compile()


AGENT_GRAPH = _build_agent_graph()


@traceable(name="smartreco_agent_pipeline", run_type="chain")
async def _run_pipeline(db, user_id: int):
    start = time.monotonic()

    user = await db.get(User, user_id)
    if user is None:
        return

    initial_state: AgentState = {
        "db": db,
        "user": user,
        "user_id": user_id,
        "start_time": start,
        "retrieval_attempts": 0,
    }
    await AGENT_GRAPH.ainvoke(initial_state)
