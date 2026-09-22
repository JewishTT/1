from typing import List, Optional
from pydantic import BaseModel, AnyHttpUrl, Field

class OrchestrateRequest(BaseModel):
    name: str
    keywords: List[str]
    # Make urls optional: αν λείπουν, θα γίνει auto-discovery μέσω SearXNG
    urls: Optional[List[AnyHttpUrl]] = Field(
        default=None,
        description="Optional list of target URLs; if omitted, the server will auto-discover via SearXNG",
    )
    phone: Optional[str] = None
    search_limit: int = 15
    social_limit: int = 10
    email_limit: int = 20
    phone_limit: int = 5
    hybrid_k: int = 20
    ingest_limit: int = 60
    export_limit: int = 2000
    fallback: Optional[bool] = True

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Panagiotis Drakatos",
                "keywords": ["athens", "software engineer"],
                # "urls": ["https://example.com/portfolio"],
                "search_limit": 15,
                "social_limit": 10,
                "email_limit": 20,
                "phone_limit": 5,
                "hybrid_k": 20,
                "ingest_limit": 60,
                "export_limit": 2000,
                "fallback": True,
            }
        }
