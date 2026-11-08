"""Catalog: every purchasable part with its price, grouped by category.

The solver works only with the catalog and does not know where parts came from:
the dataset, the seed files, or (later) shops.
"""

from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path

from pcbuilder.domain.models import Component, ComponentType, Offer
from pcbuilder.sources import docyx
from pcbuilder.sources.seeds import load_cases, load_coolers


class Catalog:
    def __init__(self, parts: Mapping[str, Component], offers: Mapping[str, Offer]):
        currencies = {offer.currency for offer in offers.values()}
        if len(currencies) > 1:
            # Dollars and euros cannot be added up; conversion comes first
            raise ValueError(f"Offers in several currencies: {sorted(currencies)}")
        self.currency = currencies.pop() if currencies else None

        self._offers = offers
        self._parts = parts
        # Only parts with a price: a part without one cannot be bought.
        # Within a category, cheapest first: the solver iterates in this order.
        self._by_category: dict[ComponentType, list[Component]] = {}
        for part in parts.values():
            if part.id in offers:
                self._by_category.setdefault(part.category, []).append(part)
        for candidates in self._by_category.values():
            candidates.sort(key=self.price)

    def price(self, part: Component) -> Decimal:
        return self._offers[part.id].price

    def candidates(self, category: ComponentType) -> list[Component]:
        """Purchasable parts in a category, cheapest first."""
        return self._by_category.get(category, [])

    def get(self, part_id: str) -> Component:
        return self._parts[part_id]

    def find(self, category: ComponentType, name: str) -> Component:
        """Cheapest part in a category with this name (case-insensitive)."""
        for part in self.candidates(category):
            if part.name.lower() == name.lower():
                return part
        raise LookupError(f"No {category} named {name!r} with a price")

    def summary(self) -> dict[ComponentType, int]:
        return {category: len(parts) for category, parts in self._by_category.items()}


# Dataset category -> parser function
DOCYX_FILES = {
    "cpu": docyx.parse_cpu,
    "motherboard": docyx.parse_motherboard,
    "memory": docyx.parse_memory,
    "video-card": docyx.parse_gpu,
    "power-supply": docyx.parse_power_supply,
    "internal-hard-drive": docyx.parse_storage,
}


def load_catalog(dataset: Path) -> Catalog:
    """Build the catalog from the docyx dataset (parts and prices) and seed files (cases, coolers)."""
    jsonl = dataset / "data" / "jsonl"
    parts: dict[str, Component] = {}
    offers: dict[str, Offer] = {}

    for name, parse in DOCYX_FILES.items():
        path = jsonl / f"{name}.jsonl"
        loaded, _ = docyx.load_parts(path, parse)
        parts.update(loaded)
        offers.update(docyx.load_offers(path, parse))

    for seeded, filename in ((load_cases(), "case"), (load_coolers(), "cpu-cooler")):
        parts.update(seeded)
        offers.update(docyx.load_offers_by_name(jsonl / f"{filename}.jsonl", seeded))

    return Catalog(parts, offers)
