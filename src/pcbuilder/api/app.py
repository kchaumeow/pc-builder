"""HTTP API и веб-страница.

Запуск из корня проекта:
    uvicorn pcbuilder.api.app:app --reload

Каталог загружается один раз при старте из датасета по пути DOCYX_PATH
(по умолчанию ~/projects/pc-part-dataset).
"""

import os
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse

from pcbuilder.api.schemas import (
    BuildRequest,
    BuildResponse,
    CatalogSummary,
    IssueView,
    ProfileName,
)
from pcbuilder.api.views import CATEGORY_LABELS, part_views
from pcbuilder.catalog import Catalog, load_catalog
from pcbuilder.recommender.budget import best_build
from pcbuilder.recommender.scores import GAMING, WORKSTATION
from pcbuilder.recommender.solver import Requirements

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

PROFILES = {
    ProfileName.GAMING: GAMING,
    ProfileName.WORK: WORKSTATION,
}


def default_catalog() -> Catalog:
    dataset = Path(
        os.environ.get("DOCYX_PATH", "~/projects/pc-part-dataset")
    ).expanduser()
    return load_catalog(dataset)


def get_catalog(request: Request) -> Catalog:
    return request.app.state.catalog


# Зависимость: FastAPI сам вызовет get_catalog и подставит каталог в параметр
CatalogDep = Annotated[Catalog, Depends(get_catalog)]


def create_app(catalog_factory: Callable[[], Catalog] = default_catalog) -> FastAPI:
    """Фабрика приложения. В тестах сюда передаётся маленький каталог вместо датасета."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        # Каталог загружается один раз при старте, а не на каждый запрос
        app.state.catalog = catalog_factory()
        yield

    app = FastAPI(title="pcbuilder", lifespan=lifespan)

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/catalog", response_model=CatalogSummary)
    def catalog_summary(catalog: CatalogDep) -> CatalogSummary:
        return CatalogSummary(
            currency=catalog.currency,
            categories={CATEGORY_LABELS[c][0]: n for c, n in catalog.summary().items()},
        )

    @app.post("/api/builds", response_model=BuildResponse)
    def create_build(request: BuildRequest, catalog: CatalogDep) -> BuildResponse:
        requirements = Requirements(
            min_ram_gb=request.min_ram_gb, min_storage_gb=request.min_storage_gb
        )
        profile = PROFILES[request.profile]

        result = best_build(catalog, request.budget, profile, requirements)
        if result is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"В {request.budget} {catalog.currency} не укладывается ни одна совместимая сборка "
                    "с такими требованиями. Увеличьте бюджет или уменьшите память и накопитель."
                ),
            )

        solution = result.solution
        return BuildResponse(
            budget=request.budget,
            total=solution.total,
            currency=catalog.currency or "",
            profile=request.profile,
            score=round(result.score, 1),
            requirements=requirements.describe(),
            parts=part_views(solution.build, catalog),
            issues=[
                IssueView(severity=i.severity, rule=i.rule, message=i.message)
                for i in solution.issues
            ],
        )

    return app


app = create_app()
