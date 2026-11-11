"""formform's addition to the Onyx API server.

Loaded instead of ``onyx.main:app`` (see docker-compose.formform.yml). It builds the stock
application and adds two read-only routes that need no LLM:

  POST /formform/context   several queries -> merged, size-bounded passages (hybrid retrieval only)
  GET  /formform/sources   connectors the caller can read, with their indexing status

Only Onyx's MIT-licensed community modules are imported (nothing from ``ee``).
"""

from datetime import datetime

from fastapi import APIRouter, Depends, FastAPI
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from onyx.auth.permissions import require_permission
from onyx.context.search.models import ChunkSearchRequest
from onyx.context.search.pipeline import search_pipeline
from onyx.configs.constants import DocumentSource
from onyx.db.connector_credential_pair import (
    CCPairAccessLevel,
    get_connector_credential_pairs_for_user,
)
from onyx.db.document import get_document_counts_for_all_cc_pairs
from onyx.db.engine.sql_engine import get_session
from onyx.db.enums import Permission
from onyx.db.models import User
from onyx.db.search_settings import get_current_search_settings
from onyx.document_index.factory import get_default_document_index
from onyx.main import app as stock_application_factory
from onyx.server.auth_check import check_router_auth
from onyx.server.utils_vector_db import require_vector_db

router = APIRouter(prefix="/formform")


class ContextRequest(BaseModel):
    queries: list[str] = Field(min_length=1, max_length=8)
    # Chunks fetched per query, and the cap on the total text returned.
    limit: int = Field(default=6, ge=1, le=20)
    max_chars: int = Field(default=12000, ge=500, le=60000)


class Passage(BaseModel):
    title: str
    source: str
    link: str | None
    content: str


class ContextResponse(BaseModel):
    passages: list[Passage]


class SourceStatus(BaseModel):
    id: int
    name: str
    source: str
    status: str
    docs: int
    last_indexed: datetime | None


def merge_ranked(ranked: list[list], key, size, max_chars: int) -> list:
    """Round-robin over per-query rankings, without duplicates, until max_chars is spent."""
    out, seen, used = [], set(), 0
    for rank in range(max((len(r) for r in ranked), default=0)):
        for results in ranked:
            if rank >= len(results) or key(results[rank]) in seen:
                continue
            seen.add(key(results[rank]))
            if used + size(results[rank]) > max_chars:
                continue
            used += size(results[rank])
            out.append(results[rank])
    return out


@router.post("/context", dependencies=[Depends(require_vector_db)])
def context(
    request: ContextRequest,
    user: User = Depends(require_permission(Permission.READ_SEARCH)),
    db_session: Session = Depends(get_session),
) -> ContextResponse:
    document_index = get_default_document_index(
        get_current_search_settings(db_session), None
    )
    # ponytail: queries run one after another; pass prefetched ACLs and run them
    # in parallel if Fill latency with many queries becomes a problem.
    ranked = [
        search_pipeline(
            chunk_search_request=ChunkSearchRequest(query=query, limit=request.limit),
            document_index=document_index,
            user=user,  # results are filtered by this user's document permissions
            persona_search_info=None,
            db_session=db_session,
        )
        for query in (q.strip()[:2048] for q in request.queries)
        if query
    ]
    chunks = merge_ranked(
        ranked,
        key=lambda c: (c.document_id, c.chunk_id),
        size=lambda c: len(c.content),
        max_chars=request.max_chars,
    )
    return ContextResponse(
        passages=[
            Passage(
                title=c.semantic_identifier or c.title or "",
                source=c.source_type.value,
                link=next(iter((c.source_links or {}).values()), None),
                content=c.content,
            )
            for c in chunks
        ]
    )


@router.get("/sources")
def sources(
    user: User = Depends(require_permission(Permission.READ_SEARCH)),
    db_session: Session = Depends(get_session),
) -> list[SourceStatus]:
    pairs = get_connector_credential_pairs_for_user(
        db_session=db_session,
        user=user,
        access_level=CCPairAccessLevel.READ,
        eager_load_connector=True,
    )
    counts = {
        (connector_id, credential_id): count
        for connector_id, credential_id, count in get_document_counts_for_all_cc_pairs(
            db_session
        )
    }
    statuses = [
        SourceStatus(
            id=p.id,
            name=p.name,
            source=p.connector.source.value,
            status=p.status.value,
            docs=counts.get((p.connector_id, p.credential_id), 0),
            last_indexed=p.last_successful_index_time,
        )
        for p in pairs
        if p.connector is not None
    ]
    # Onyx ships an empty pair for its ingestion API; show it only once it holds documents.
    return [
        s
        for s in statuses
        if s.docs or s.source != DocumentSource.INGESTION_API.value
    ]


def app() -> FastAPI:
    application = stock_application_factory()
    # nginx strips /api before proxying, same as for every stock route.
    application.include_router(router)
    check_router_auth(application)  # fail at startup if a route above lost its auth dependency
    return application


if __name__ == "__main__":
    # Self-check of the only logic here that is not Onyx's: python -m formform_onyx.app
    merged = merge_ranked([["a1", "b22", "c333"], ["b22", "d4444"]], key=str, size=len, max_chars=10)
    assert merged == ["a1", "b22", "d4444"], merged
    print("ok")
