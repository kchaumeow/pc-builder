import pytest

from pcbuilder.domain.models import MemoryType
from pcbuilder.sources.docyx import parse_memory

VENGEANCE_RGB = {
    "name": "Corsair Vengeance RGB 32 GB", "price": 94.99,
    "speed": [5, 6000], "modules": [2, 16], "price_per_gb": 2.968,
    "color": "Black", "first_word_latency": 12, "cas_latency": 36,
}


def test_parse_memory():
    ram = parse_memory(VENGEANCE_RGB)
    assert ram.id == "ram-corsair-vengeance-rgb-32-gb-ddr5-6000-2x16-cl36-black"
    assert ram.brand == "Corsair"
    assert ram.model == "Vengeance RGB 32 GB"
    assert ram.memory_type == MemoryType.DDR5
    assert ram.speed_mhz == 6000
    assert ram.modules == 2
    assert ram.capacity_gb == 32   # суммарно: 2 × 16, а не 16
    assert ram.cas_latency == 36


def test_parse_memory_four_modules():
    # Ловит len(modules): у списка [4, 8] длина 2, а планок 4
    ram = parse_memory({**VENGEANCE_RGB, "modules": [4, 8]})
    assert ram.modules == 4
    assert ram.capacity_gb == 32


def test_parse_memory_unknown_ddr_version_is_rejected():
    with pytest.raises(ValueError):
        parse_memory({**VENGEANCE_RGB, "speed": [6, 8000]})