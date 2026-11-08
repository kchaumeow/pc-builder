from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from pcbuilder.api.app import create_app
from tests.test_budget import CPU, FAST_GPU, SLOW_GPU
from tests.test_compatibility import make_motherboard
from tests.test_solver import BASE, named, priced

# Intel motherboard: doesn't fit the catalog's AM5 CPU
INTEL_BOARD = named(make_motherboard, "mb-intel", socket="LGA1700").model_copy(
    update={"model": "Z790 Tomahawk"}
)
FULL_BUILD = ["cpu", "gpu-fast", "mb", "ram", "ssd", "psu", "case", "cooler"]


def catalog():
    return priced(
        (CPU, "200"), (FAST_GPU, "900"), (SLOW_GPU, "300"), (INTEL_BOARD, "120"), *BASE
    )


@pytest.fixture
def client():
    # with — so lifespan runs and the catalog gets loaded
    with TestClient(create_app(catalog_factory=catalog)) as client:
        yield client


def test_index_serves_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_catalog_summary(client):
    assert client.get("/api/catalog").json() == {
        "currency": "USD",
        "categories": {
            "cpu": 1,
            "gpu": 2,
            "motherboard": 2,
            "ram": 1,
            "storage": 1,
            "psu": 1,
            "case": 1,
            "cooling": 1,
        },
    }


def test_build_within_budget(client):
    response = client.post("/api/builds", json={"budget": "2000"})
    assert response.status_code == 200
    build = response.json()
    assert Decimal(build["total"]) == Decimal(1620)  # 200 + 900 + 520
    assert build["currency"] == "USD"
    assert build["profile"] == "gaming"
    assert build["issues"] == []

    parts = {part["category"]: part for part in build["parts"]}
    assert parts["gpu"]["id"] == "gpu-fast"
    assert parts["gpu"]["label"] == "Graphics card"
    assert sum(Decimal(p["price"]) for p in build["parts"]) == Decimal(build["total"])


def test_parts_in_reading_order(client):
    build = client.post("/api/builds", json={"budget": "2000"}).json()
    assert [part["category"] for part in build["parts"]] == [
        "cpu",
        "gpu",
        "motherboard",
        "ram",
        "storage",
        "psu",
        "case",
        "cooling",
    ]


def test_work_profile(client):
    response = client.post("/api/builds", json={"budget": "2000", "profile": "work"})
    assert response.status_code == 200
    assert response.json()["profile"] == "work"


def test_budget_too_small_is_404_with_explanation(client):
    response = client.post("/api/builds", json={"budget": "500"})
    assert response.status_code == 404
    assert "500 USD" in response.json()["detail"]


@pytest.mark.parametrize(
    "body",
    [
        {"budget": "0"},
        {"budget": "-100"},
        {"budget": "200000"},
        {"budget": "1000", "profile": "mining"},
        {"budget": "1000", "min_ram_gb": 4},
        {"budget": "1000", "min_storage_gb": 64},
        {},
    ],
)
def test_invalid_request_is_422(client, body):
    assert client.post("/api/builds", json=body).status_code == 422


# --- Custom build --------------------------------------------------------------


def check(client, part_ids):
    return client.post("/api/builds/check", json={"part_ids": part_ids})


def search(client, category, part_ids=(), **kwargs):
    body = {"category": category, "part_ids": list(part_ids), **kwargs}
    return client.post("/api/parts/search", json=body)


def test_check_empty_build(client):
    view = check(client, []).json()
    assert view["parts"] == []
    assert Decimal(view["total"]) == 0
    assert view["missing"] == [
        "cpu",
        "motherboard",
        "ram",
        "storage",
        "psu",
        "case",
        "cooling",
    ]
    assert view["complete"] is False


def test_check_full_build(client):
    view = check(client, FULL_BUILD).json()
    assert view["missing"] == []
    assert view["issues"] == []
    assert view["complete"] is True
    assert Decimal(view["total"]) == Decimal(1620)


def test_check_reports_incompatible_parts(client):
    view = check(client, ["cpu", "mb-intel"]).json()
    assert any(issue["severity"] == "ERROR" for issue in view["issues"])
    assert view["complete"] is False


def test_part_of_same_category_replaces_previous(client):
    view = check(client, ["cpu", "mb", "mb-intel"]).json()
    assert [p["id"] for p in view["parts"] if p["category"] == "motherboard"] == [
        "mb-intel"
    ]


def test_drives_are_added_not_replaced(client):
    view = check(client, ["ssd", "ssd"]).json()
    assert [p["id"] for p in view["parts"]] == ["ssd", "ssd"]


def test_unknown_part_is_422(client):
    response = check(client, ["cpu", "no-such-part"])
    assert response.status_code == 422
    assert "no-such-part" in response.json()["detail"]


def test_search_shows_only_compatible_by_default(client):
    result = search(client, "motherboard", ["cpu"]).json()
    assert result["matched"] == 2
    assert result["compatible"] == 1
    assert [p["id"] for p in result["parts"]] == ["mb"]
    assert result["parts"][0]["compatible"] is True


def test_search_explains_incompatible(client):
    result = search(client, "motherboard", ["cpu"], include_incompatible=True).json()
    # Compatible first, even though the Intel motherboard is cheaper
    assert [p["id"] for p in result["parts"]] == ["mb", "mb-intel"]
    intel = result["parts"][1]
    assert intel["compatible"] is False
    assert any("LGA1700" in problem for problem in intel["problems"])


def test_search_with_empty_build_accepts_everything(client):
    result = search(client, "motherboard").json()
    assert result["compatible"] == result["matched"] == 2
    # Without a CPU both fit — cheapest first
    assert [p["id"] for p in result["parts"]] == ["mb-intel", "mb"]


def test_search_by_name(client):
    result = search(client, "motherboard", query="z790 TOMAHAWK").json()
    assert [p["id"] for p in result["parts"]] == ["mb-intel"]
    assert search(client, "motherboard", query="nothing").json()["matched"] == 0


def test_search_respects_limit(client):
    result = search(client, "gpu", limit=1).json()
    assert result["matched"] == 2
    assert len(result["parts"]) == 1


def test_search_unknown_category_is_422(client):
    assert search(client, "monitor").status_code == 422


def test_complete_keeps_chosen_parts(client):
    response = client.post(
        "/api/builds/complete", json={"part_ids": ["cpu", "gpu-slow"]}
    )
    assert response.status_code == 200
    view = response.json()
    ids = {p["id"] for p in view["parts"]}
    assert {"cpu", "gpu-slow"} <= ids
    assert "mb-intel" not in ids
    assert view["complete"] is True
    assert view["missing"] == []


def test_complete_incompatible_start_is_404(client):
    response = client.post(
        "/api/builds/complete", json={"part_ids": ["cpu", "mb-intel"]}
    )
    assert response.status_code == 404
    assert "incompatible" in response.json()["detail"]
