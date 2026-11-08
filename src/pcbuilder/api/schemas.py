"""API request and response schemas.

Kept separate from the domain models: the API returns what the page needs (labels,
totals) and can change independently of how parts are modeled internally.
"""

from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field


class ProfileName(StrEnum):
    GAMING = "gaming"
    WORK = "work"


class BuildRequest(BaseModel):
    budget: Decimal = Field(
        gt=0, le=100_000, description="Budget in the catalog currency"
    )
    profile: ProfileName = ProfileName.GAMING
    min_ram_gb: int = Field(default=32, ge=8, le=256)
    min_storage_gb: int = Field(default=1000, ge=128, le=16_000)


class PartView(BaseModel):
    category: str  # category key: "cpu", "gpu", ...
    label: str  # human-readable label: "CPU"
    id: str
    name: str
    details: str  # key specs in one line
    price: Decimal


class IssueView(BaseModel):
    severity: str
    rule: str
    message: str


class BuildResponse(BaseModel):
    budget: Decimal
    total: Decimal
    currency: str
    profile: ProfileName
    score: float
    requirements: str
    parts: list[PartView]
    issues: list[IssueView]


class CatalogSummary(BaseModel):
    currency: str | None
    categories: dict[str, int]


# --- Builder: a build part by part --------------------------------------------
# The page keeps the build as a list of part ids; the server rebuilds it on every request.


class CategoryKey(StrEnum):
    CPU = "cpu"
    GPU = "gpu"
    MOTHERBOARD = "motherboard"
    RAM = "ram"
    STORAGE = "storage"
    PSU = "psu"
    CASE = "case"
    COOLING = "cooling"


PartIds = Annotated[list[str], Field(default_factory=list, max_length=20)]


class BuildCheckRequest(BaseModel):
    part_ids: PartIds


class BuildCompleteRequest(BaseModel):
    part_ids: PartIds
    min_ram_gb: int = Field(default=32, ge=8, le=256)
    min_storage_gb: int = Field(default=1000, ge=128, le=16_000)


class BuildCheckResponse(BaseModel):
    total: Decimal
    currency: str
    parts: list[PartView]
    issues: list[IssueView]
    missing: list[CategoryKey]  # which parts are still missing
    complete: bool  # nothing missing and no errors


class PartSearchRequest(BaseModel):
    category: CategoryKey
    part_ids: PartIds  # current build: compatibility is checked against it
    query: str = Field(default="", max_length=100)
    include_incompatible: bool = False
    limit: int = Field(default=30, ge=1, le=100)


class CandidateView(PartView):
    compatible: bool
    problems: list[str]  # what breaks if the part is added


class PartSearchResponse(BaseModel):
    matched: int  # how many parts matched the query
    compatible: int  # how many of those fit the current build
    parts: list[CandidateView]
