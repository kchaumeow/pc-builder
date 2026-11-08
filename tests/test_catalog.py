from decimal import Decimal

import pytest

from pcbuilder.catalog import Catalog
from pcbuilder.domain.models import ComponentType, Cooling, Offer


def cooler(part_id: str, model: str) -> Cooling:
    return Cooling(
        id=part_id, brand="Test", model=model, sockets=["AM5"], height_mm=150
    )


def offer(part_id: str, price: str, currency: str = "USD") -> Offer:
    return Offer(
        part_id=part_id, source="test", price=Decimal(price), currency=currency
    )


PARTS = {
    "c-mid": cooler("c-mid", "Mid"),
    "c-cheap": cooler("c-cheap", "Cheap"),
    "c-pricey": cooler("c-pricey", "Pricey"),
    "c-noprice": cooler("c-noprice", "No Price"),
}
OFFERS = {
    "c-mid": offer("c-mid", "40"),
    "c-cheap": offer("c-cheap", "20"),
    "c-pricey": offer("c-pricey", "90"),
}


def test_candidates_sorted_by_price():
    catalog = Catalog(PARTS, OFFERS)
    ids = [p.id for p in catalog.candidates(ComponentType.COOLING)]
    assert ids == ["c-cheap", "c-mid", "c-pricey"]


def test_parts_without_price_are_not_candidates():
    catalog = Catalog(PARTS, OFFERS)
    assert "c-noprice" not in [p.id for p in catalog.candidates(ComponentType.COOLING)]
    # но сама деталь в каталоге есть — её можно найти по id
    assert catalog.get("c-noprice").model == "No Price"


def test_empty_category():
    assert Catalog(PARTS, OFFERS).candidates(ComponentType.GPU) == []


def test_price():
    catalog = Catalog(PARTS, OFFERS)
    assert catalog.price(PARTS["c-mid"]) == Decimal(40)


def test_find_by_name_ignores_case():
    catalog = Catalog(PARTS, OFFERS)
    assert catalog.find(ComponentType.COOLING, "test MID").id == "c-mid"


def test_find_missing_raises():
    with pytest.raises(LookupError):
        Catalog(PARTS, OFFERS).find(ComponentType.COOLING, "Nope")


def test_mixed_currencies_rejected():
    offers = {**OFFERS, "c-mid": offer("c-mid", "40", currency="EUR")}
    with pytest.raises(ValueError, match="currencies"):
        Catalog(PARTS, offers)
