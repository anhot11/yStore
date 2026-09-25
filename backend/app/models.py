from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class GameItem(BaseModel):
    id: str
    title: str
    source: Literal["fdroid", "itchio"]
    icon_url: Optional[str] = None
    screenshots: List[str] = Field(default_factory=list)
    description: str = ""
    developer: str = ""
    download_url: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class CatalogQuery(BaseModel):
    source: Optional[Literal["fdroid", "itchio", "all"]] = None
    tag: Optional[str] = None
    page: int = 1
