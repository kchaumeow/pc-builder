"""HTTP API and web page.

Run from the project root:
    uvicorn pcbuilder.api.app:app --reload

The catalog is loaded once at startup from the dataset at DOCYX_PATH
(default: ~/projects/pc-part-dataset).
"""

import os
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse

from pcbuilder.api import builder
from pcbuilder.api.schemas import (
    BuildCheckRequest,
    BuildCheckResponse,
    BuildCompleteRequest,
    BuildRequest,
    BuildResponse,
    CandidateView,
    CatalogSummary,
    IssueView,
    PartSearchRequest,
    PartSearchResponse,
    ProfileName,
)
from pcbuilder.api.views import CATEGORY_LABELS, part_view, part_views
from pcbuilder.catalog import Catalog, load_catalog
from pcbuilder.domain.compatibility import Issue, check
from pcbuilder.domain.models import Build
from pcbuilder.recommender.budget import best_build
from pcbuilder.recommender.scores import GAMING, WORKSTATION
from pcbuilder.recommender.solver import Requirements, Solver, has_errors

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


# Dependency: FastAPI calls get_catalog itself and injects the catalog into the parameter
CatalogDep = Annotated[Catalog, Depends(get_catalog)]


def issue_views(issues: list[Issue]) -> list[IssueView]:
    return [
        IssueView(severity=i.severity, rule=i.rule, message=i.message) for i in issues
    ]


def load_build(catalog: Catalog, part_ids: list[str]) -> Build:
    try:
        return builder.build_from_ids(catalog, part_ids)
    except builder.UnknownPart as e:
        raise HTTPException(
            status_code=422, detail=f"No such part in the catalog: {e}"
        ) from e


def build_check_view(build: Build, catalog: Catalog) -> BuildCheckResponse:
    missing = builder.missing(build)
    issues = check(build, complete=not missing)
    parts = part_views(build, catalog)
    return BuildCheckResponse(
        total=sum((p.price for p in parts), Decimal(0)),
        currency=catalog.currency or "",
        parts=parts,
        issues=issue_views(issues),
        missing=missing,
        complete=not missing and not has_errors(issues),
    )


def create_app(catalog_factory: Callable[[], Catalog] = default_catalog) -> FastAPI:
    """App factory. Tests pass a small catalog here instead of the dataset."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        # The catalog is loaded once at startup, not on every request
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
                    "No compatible build with these requirements fits into "
                    f"{request.budget} {catalog.currency}. Raise the budget or lower "
                    "the memory and storage requirements."
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
            issues=issue_views(solution.issues),
        )

    @app.post("/api/builds/check", response_model=BuildCheckResponse)
    def check_build(
        request: BuildCheckRequest, catalog: CatalogDep
    ) -> BuildCheckResponse:
        return build_check_view(load_build(catalog, request.part_ids), catalog)

    @app.post("/api/builds/complete", response_model=BuildCheckResponse)
    def complete_build(
        request: BuildCompleteRequest, catalog: CatalogDep
    ) -> BuildCheckResponse:
        build = load_build(catalog, request.part_ids)
        requirements = Requirements(
            min_ram_gb=request.min_ram_gb, min_storage_gb=request.min_storage_gb
        )
        solution = Solver(catalog, requirements).complete(build)
        if solution is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Can't complete the build: the chosen parts are incompatible with each "
                    "other, or no parts match the requirements. If the CPU has no integrated "
                    "graphics, choose a graphics card first — the builder doesn't pick one."
                ),
            )
        return build_check_view(solution.build, catalog)

    @app.post("/api/parts/search", response_model=PartSearchResponse)
    def search_parts(
        request: PartSearchRequest, catalog: CatalogDep
    ) -> PartSearchResponse:
        result = builder.search(
            catalog,
            load_build(catalog, request.part_ids),
            builder.KEY_TO_CATEGORY[request.category],
            query=request.query,
            include_incompatible=request.include_incompatible,
            limit=request.limit,
        )
        return PartSearchResponse(
            matched=result.matched,
            compatible=result.compatible,
            parts=[
                CandidateView(
                    **part_view(c.part, catalog).model_dump(),
                    compatible=c.compatible,
                    problems=[issue.message for issue in c.problems],
                )
                for c in result.candidates
            ],
        )

    return app


app = create_app()
