from typing import Literal

from pydantic import BaseModel, Field

TripletKey = tuple[str, str, str | None]


class ConceptTriplet(BaseModel):
    code: str = Field(frozen=True)
    system: str = Field(frozen=True)
    version: str | None = Field(frozen=True)

    original_display: str
    display: dict[str, str] = {}

    @property
    def key(self) -> TripletKey:
        return self.code, self.system, self.version


# Slim read-only view of a cached, already expanded ValueSet
# to try to avoid pydantic loading times.
class CachedConcept(BaseModel):
    code: str | None = None
    system: str | None = None
    version: str | None = None
    display: str | None = None


class CachedExpansion(BaseModel):
    total: int | None = None
    contains: list[CachedConcept] | None = None


class CachedValueSet(BaseModel):
    url: str | None = None
    version: str | None = None
    expansion: CachedExpansion | None = None
