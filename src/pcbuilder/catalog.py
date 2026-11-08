"""Каталог: все детали, которые можно купить, с ценами, по категориям.

Солвер работает только с каталогом и не знает, откуда пришли детали —
из датасета, справочников или (позже) из магазинов.
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
            # Складывать доллары с евро нельзя — сначала нужна конвертация
            raise ValueError(f"Offers in several currencies: {sorted(currencies)}")
        self.currency = currencies.pop() if currencies else None

        self._offers = offers
        self._parts = parts
        # Только детали с ценой: без цены деталь нельзя купить.
        # Внутри категории — от дешёвых к дорогим: солвер будет перебирать в этом порядке.
        self._by_category: dict[ComponentType, list[Component]] = {}
        for part in parts.values():
            if part.id in offers:
                self._by_category.setdefault(part.category, []).append(part)
        for candidates in self._by_category.values():
            candidates.sort(key=self.price)

    def price(self, part: Component) -> Decimal:
        return self._offers[part.id].price

    def candidates(self, category: ComponentType) -> list[Component]:
        """Детали категории, которые можно купить, от дешёвых к дорогим."""
        return self._by_category.get(category, [])

    def get(self, part_id: str) -> Component:
        return self._parts[part_id]

    def find(self, category: ComponentType, name: str) -> Component:
        """Самая дешёвая деталь категории с таким названием (без учёта регистра)."""
        for part in self.candidates(category):
            if part.name.lower() == name.lower():
                return part
        raise LookupError(f"No {category} named {name!r} with a price")

    def summary(self) -> dict[ComponentType, int]:
        return {category: len(parts) for category, parts in self._by_category.items()}


# Категория датасета → функция разбора
DOCYX_FILES = {
    "cpu": docyx.parse_cpu,
    "motherboard": docyx.parse_motherboard,
    "memory": docyx.parse_memory,
    "video-card": docyx.parse_gpu,
    "power-supply": docyx.parse_power_supply,
    "internal-hard-drive": docyx.parse_storage,
}


def load_catalog(dataset: Path) -> Catalog:
    """Собрать каталог из датасета docyx (детали и цены) и справочников (корпуса, кулеры)."""
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
