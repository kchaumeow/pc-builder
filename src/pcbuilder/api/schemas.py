"""Схемы запросов и ответов API.

Отдельно от доменных моделей: API отдаёт то, что нужно странице (подписи, итоги),
и может меняться независимо от того, как детали устроены внутри.
"""

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field


class ProfileName(StrEnum):
    GAMING = "gaming"
    WORK = "work"


class BuildRequest(BaseModel):
    budget: Decimal = Field(gt=0, le=100_000, description="Бюджет в валюте каталога")
    profile: ProfileName = ProfileName.GAMING
    min_ram_gb: int = Field(default=32, ge=8, le=256)
    min_storage_gb: int = Field(default=1000, ge=128, le=16_000)


class PartView(BaseModel):
    category: str  # ключ категории: "cpu", "gpu", ...
    label: str  # подпись для человека: «Процессор»
    id: str
    name: str
    details: str  # главные характеристики одной строкой
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
