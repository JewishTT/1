from __future__ import annotations
from typing import List, Optional, Literal
from pydantic import BaseModel, Field

class SearchRequest(BaseModel):
    name: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    limit: int = Field(default=10, ge=1, le=200)
    max: bool = False
    mode: Literal["any", "all"] = "any"

class SearchResult(BaseModel):
    url: str
    title: str
    snippet: Optional[str] = None
    source: Literal["google", "searxng"]
    rank: Optional[int] = None
    rrf: Optional[float] = None

class IngestRequest(BaseModel):
    urls: List[str]
    source: Optional[str] = None
    text: Optional[str] = None

class HybridSearchRequest(BaseModel):
    query: str
    k: int = Field(default=10, ge=1, le=200)

class OrchestrateRequest(BaseModel):
    name: str
    keywords: List[str] = Field(default_factory=list)
    phone: Optional[str] = None
    search_limit: int = 15
    social_limit: int = 10
    email_limit: int = 20
    phone_limit: int = 5
    hybrid_k: int = 20
    ingest_limit: int = 60
    export_limit: int = 2000

