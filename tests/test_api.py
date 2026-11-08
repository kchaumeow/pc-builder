from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from pcbuilder.api.app import create_app
from tests.test_budget import catalog


@pytest.fixture
def client():
    # with — чтобы отработал lifespan и каталог загрузился
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
            "motherboard": 1,
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
    assert parts["gpu"]["label"] == "Видеокарта"
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
