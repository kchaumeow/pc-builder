"""Seed file tests: they check the data in data/seeds, not the code.

If someone makes a mistake while filling them in (a form factor typo, height 1550
instead of 155), these tests fail before the error reaches the build picker.
"""

import json

import pytest

from pcbuilder.domain.models import Case, Cooling
from pcbuilder.sources.docyx import SUPPORTED_SOCKETS
from pcbuilder.sources.seeds import SEEDS_DIR, load_cases, load_coolers, load_seed

CASES = load_cases()
COOLERS = load_coolers()


def test_seeds_are_not_empty():
    assert len(CASES) >= 10
    assert len(COOLERS) >= 10


# --- Cases --------------------------------------------------------------------------


@pytest.mark.parametrize("case", CASES.values(), ids=lambda c: c.id)
def test_case_limits_are_plausible(case: Case):
    # Guard against typos: an extra zero or a missing digit
    assert 150 <= case.max_gpu_length_mm <= 500
    assert 40 <= case.max_cooler_height_mm <= 200


# --- CPU coolers --------------------------------------------------------------------


@pytest.mark.parametrize("cooler", COOLERS.values(), ids=lambda c: c.id)
def test_cooler_is_tower_or_aio(cooler: Cooling):
    # Exactly one: tower height or AIO radiator size
    assert (cooler.height_mm is None) != (cooler.radiator_mm is None)


@pytest.mark.parametrize("cooler", COOLERS.values(), ids=lambda c: c.id)
def test_cooler_values_are_plausible(cooler: Cooling):
    if cooler.height_mm is not None:
        assert 30 <= cooler.height_mm <= 200
    if cooler.radiator_mm is not None:
        assert cooler.radiator_mm in {120, 140, 240, 280, 360, 420}


@pytest.mark.parametrize("cooler", COOLERS.values(), ids=lambda c: c.id)
def test_cooler_sockets_are_known(cooler: Cooling):
    # A typo like "LGA170" instead of "LGA1700" would silently break the socket rule
    assert set(cooler.sockets) <= SUPPORTED_SOCKETS


# --- The loader itself --------------------------------------------------------------


def test_seed_with_typo_fails_loudly(tmp_path):
    bad = {
        "items": [
            {
                "brand": "X",
                "model": "Y",
                "supported_motherboard_form_factors": ["ATX"],
                "max_gpu_length_mm": 300,
                "max_cooler_height_mm": 160,
                "psu_form_factors": ["ATXX"],
            }
        ]
    }
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="record #0"):
        load_seed(path, Case, "case")


def test_seed_duplicate_fails_loudly(tmp_path):
    item = {"brand": "X", "model": "Y", "sockets": ["AM5"], "height_mm": 150}
    path = tmp_path / "coolers.json"
    path.write_text(json.dumps({"items": [item, item]}))
    with pytest.raises(ValueError, match="duplicate"):
        load_seed(path, Cooling, "cooler")


def test_seeds_dir_exists():
    assert (SEEDS_DIR / "cases.json").exists()
    assert (SEEDS_DIR / "coolers.json").exists()
