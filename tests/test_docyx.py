import pytest

from pcbuilder.domain.models import MemoryType, MotherBoardFormFactor
from pcbuilder.sources.docyx import detect_memory_type, extract_chipset, parse_memory, parse_motherboard

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

    ram = parse_memory({**VENGEANCE_RGB, "modules": [4, 8]})
    assert ram.modules == 4
    assert ram.capacity_gb == 32


def test_parse_memory_unknown_ddr_version_is_rejected():
    with pytest.raises(ValueError):
        parse_memory({**VENGEANCE_RGB, "speed": [6, 8000]})

PRIME_B550M = {
    "name": "Asus PRIME B550M-A WIFI II", "price": 99.99, "socket": "AM4",
    "form_factor": "Micro ATX", "max_memory": 128, "memory_slots": 4,
    "color": "Blue / Silver",
}


def test_parse_motherboard():
    mb = parse_motherboard(PRIME_B550M)
    assert mb.id == "mb-asus-prime-b550m-a-wifi-ii"
    assert mb.socket == "AM4"
    assert mb.chipset == "B550"                                 # без M
    assert mb.form_factor == MotherBoardFormFactor.MICRO_ATX    # из "Micro ATX"
    assert mb.memory_type == MemoryType.DDR4                    # по сокету
    assert mb.max_memory_gb == 128
    assert mb.m2_slots is None                                  # неизвестно, а не 0


def test_parse_motherboard_rejects_old_socket():
    with pytest.raises(ValueError):
        parse_motherboard({**PRIME_B550M, "socket": "LGA1151"})

@pytest.mark.parametrize("name, expected", [
    ("Asus PRIME B650-PLUS WIFI", "B650"),
    ("MSI MAG B650 TOMAHAWK WIFI", "B650"),
    ("Gigabyte X870E AORUS ELITE WIFI7", "X870E"),
    ("Asus PRIME B550M-A WIFI II", "B550"),
    ("Gigabyte B760I AORUS PRO", "B760"),
    ("MAXSUN iCraft Z790ITX WIFI", "Z790"),
    ("Biostar B660GTA", "B660"),
    ("MSI Z790MPOWER", "Z790"),
    ("Colorful CVN Z790D5 GAMING FROZEN V20", "Z790"),
    ("MSI PRO-H610M-E-DDR4", "H610"),
    ("NZXT N7-Z69XT-B1", None),
])
def test_extract_chipset(name, expected):
    assert extract_chipset(name) == expected


@pytest.mark.parametrize("name, socket, chipset, expected", [
    ("Asus PRIME B650-PLUS WIFI", "AM5", "B650", MemoryType.DDR5),          # по сокету
    ("Asus PRIME B550M-A WIFI II", "AM4", "B550", MemoryType.DDR4),         # по сокету
    ("MSI PRO B760M-P DDR4", "LGA1700", "B760", MemoryType.DDR4),           # из названия
    ("ASRock B760 Pro RS/D4", "LGA1700", "B760", MemoryType.DDR4),          # ASRock: /D4
    ("Asus PRIME H610I-PLUS D4-CSM", "LGA1700", "H610", MemoryType.DDR4),   # ASUS: D4
    ("MSI MPG Z790I EDGE WIFI", "LGA1700", "Z790", MemoryType.DDR5),        # 700-я серия без пометки
])
def test_detect_memory_type(name, socket, chipset, expected):
    assert detect_memory_type(name, socket, chipset) == expected


@pytest.mark.parametrize("name, socket, chipset", [
    ("MSI MEG Z690I UNIFY", "LGA1700", "Z690"),        # 600-я серия без пометки — неоднозначно
    ("Biostar H610MH", "LGA1700", "H610"),             # то же
    ("Weird B650 Board DDR4", "AM5", "B650"),          # противоречие названия и сокета
])
def test_detect_memory_type_rejects(name, socket, chipset):
    with pytest.raises(ValueError):
        detect_memory_type(name, socket, chipset)