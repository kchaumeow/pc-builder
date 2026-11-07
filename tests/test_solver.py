from decimal import Decimal

import pytest

from pcbuilder.catalog import Catalog
from pcbuilder.domain.models import Build, Component, MotherBoardFormFactor, Offer
from pcbuilder.recommender.solver import Requirements, SearchLimitReached, Solver, with_part
from tests.test_compatibility import (
    make_case,
    make_cooling,
    make_cpu,
    make_gpu,
    make_motherboard,
    make_psu,
    make_ram,
    make_storage,
)


def priced(*items: tuple[Component, str]) -> Catalog:
    """Каталог из пар (деталь, цена)."""
    parts = {part.id: part for part, _ in items}
    offers = {part.id: Offer(part_id=part.id, source="test", price=Decimal(price)) for part, price in items}
    return Catalog(parts, offers)


def named(factory, part_id: str, **kwargs):
    return factory(**kwargs).model_copy(update={"id": part_id})


# Полный набор совместимых деталей по одной на категорию
BASE = [
    (named(make_motherboard, "mb"), "150"),
    (named(make_ram, "ram"), "100"),
    (named(make_storage, "ssd"), "80"),
    (named(make_psu, "psu"), "90"),
    (named(make_case, "case"), "70"),
    (named(make_cooling, "cooler"), "30"),
]
START = Build(cpu=make_cpu(includes_cooler=False), gpu=make_gpu())


def test_completes_build():
    catalog = priced((START.cpu, "200"), (START.gpu, "500"), *BASE)
    solution = Solver(catalog).complete(START)
    assert solution is not None
    assert solution.build.motherboard.id == "mb"
    assert solution.build.cooling.id == "cooler"
    assert solution.total == Decimal("1220")
    assert solution.issues == []


def test_keeps_chosen_parts():
    catalog = priced((START.cpu, "200"), (START.gpu, "500"), *BASE)
    solution = Solver(catalog).complete(START)
    assert solution.build.cpu == START.cpu
    assert solution.build.gpu == START.gpu


def test_skips_cheaper_incompatible_part():
    cheap_wrong_socket = (named(make_motherboard, "mb-lga", socket="LGA1700"), "50")
    catalog = priced((START.cpu, "200"), (START.gpu, "500"), cheap_wrong_socket, *BASE)
    assert Solver(catalog).complete(START).build.motherboard.id == "mb"


def test_backtracks_when_later_category_fails():
    # Самая дешёвая плата — ATX, но единственный корпус принимает только Micro-ATX.
    # Выбор платы нужно пересмотреть, когда дело дойдёт до корпуса.
    atx = (named(make_motherboard, "mb-atx", form_factor=MotherBoardFormFactor.ATX), "100")
    matx = (named(make_motherboard, "mb-matx", form_factor=MotherBoardFormFactor.MICRO_ATX), "130")
    small_case = (named(make_case, "case-matx",
                        supported_motherboard_form_factors=[MotherBoardFormFactor.MICRO_ATX]), "70")
    others = [item for item in BASE if item[0].id not in ("mb", "case")]
    catalog = priced((START.cpu, "200"), (START.gpu, "500"), atx, matx, small_case, *others)

    solution = Solver(catalog).complete(START)
    assert solution.build.motherboard.id == "mb-matx"


def test_requirements_filter_parts():
    small_ram = (named(make_ram, "ram-16", capacity_gb=16), "50")
    catalog = priced((START.cpu, "200"), (START.gpu, "500"), small_ram, *BASE)
    assert Solver(catalog).complete(START).build.ram.id == "ram-16"
    picky = Solver(catalog, Requirements(min_ram_gb=32))
    assert picky.complete(START).build.ram.id == "ram"


def test_boxed_cooler_needs_no_cooler():
    start = Build(cpu=make_cpu(includes_cooler=True), gpu=make_gpu())
    catalog = priced((start.cpu, "200"), (start.gpu, "500"), *BASE)
    assert Solver(catalog).complete(start).build.cooling is None


def test_no_solution_returns_none():
    weak_psu = (named(make_psu, "psu-weak", wattage_w=200), "40")
    others = [item for item in BASE if item[0].id != "psu"]
    catalog = priced((START.cpu, "200"), (START.gpu, "500"), weak_psu, *others)
    assert Solver(catalog).complete(START) is None


def test_incompatible_start_returns_none():
    start = START.model_copy(update={"motherboard": make_motherboard(socket="LGA1700")})
    catalog = priced((START.cpu, "200"), (START.gpu, "500"), *BASE)
    assert Solver(catalog).complete(start) is None


def test_search_limit():
    catalog = priced((START.cpu, "200"), (START.gpu, "500"), *BASE)
    with pytest.raises(SearchLimitReached):
        Solver(catalog, max_steps=3).complete(START)


def test_with_part_does_not_change_original():
    build = Build()
    with_part(build, make_ram())
    assert build.ram is None