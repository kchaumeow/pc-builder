import pytest

from pcbuilder.domain.models import (
    MemoryType,
    MotherBoardFormFactor,
    PsuEfficiency,
    PsuFormFactor,
    PsuModularity,
    StorageFormFactor,
    StorageInterface,
    StorageMedia,
)
from pcbuilder.sources.docyx import (
    detect_memory_type,
    extract_chipset,
    ghz_to_mhz,
    parse_cpu,
    parse_gpu,
    parse_memory,
    parse_motherboard,
    parse_power_supply,
    parse_storage,
    slugify,
)

# Записи — реальные строки из датасета


# --- Общее -------------------------------------------------------------------------


@pytest.mark.parametrize("text, expected", [
    ("Corsair Vengeance RGB 32 GB", "corsair-vengeance-rgb-32-gb"),
    ("G.Skill Flare X5 32 GB", "g-skill-flare-x5-32-gb"),
    ("Black / Yellow", "black-yellow"),
    ("  (rev. 1.0)  ", "rev-1-0"),
    ("Kingston SSDNow V+", "kingston-ssdnow-v-plus"),   # иначе совпало бы с «SSDNow V»
])
def test_slugify(text, expected):
    assert slugify(text) == expected


# --- Память ------------------------------------------------------------------------

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
    assert ram.capacity_gb == 32  # суммарно: 2 × 16, а не 16
    assert ram.cas_latency == 36


def test_parse_memory_four_modules():
    # Ловит len(modules): у списка [4, 8] длина 2, а планок 4
    ram = parse_memory({**VENGEANCE_RGB, "modules": [4, 8]})
    assert ram.modules == 4
    assert ram.capacity_gb == 32


def test_same_name_different_speed_gets_different_id():
    # Под одним названием продаются разные комплекты
    a = parse_memory(VENGEANCE_RGB)
    b = parse_memory({**VENGEANCE_RGB, "speed": [5, 5600]})
    assert a.id != b.id


def test_parse_memory_without_cas_latency():
    record = {k: v for k, v in VENGEANCE_RGB.items() if k != "cas_latency"}
    assert parse_memory(record).cas_latency is None


def test_parse_memory_unknown_ddr_version_is_rejected():
    with pytest.raises(ValueError):
        parse_memory({**VENGEANCE_RGB, "speed": [6, 8000]})


def test_parse_memory_speed_without_version_is_rejected():
    # DDR1 в датасете: speed — одно число, а не пара
    with pytest.raises(ValueError):
        parse_memory({**VENGEANCE_RGB, "speed": 400})


# --- Процессоры --------------------------------------------------------------------

RYZEN_9800X3D = {
    "name": "AMD Ryzen 7 9800X3D", "price": 451.5, "core_count": 8,
    "core_clock": 4.7, "boost_clock": 5.2, "microarchitecture": "Zen 5",
    "tdp": 120, "graphics": "Radeon",
}


def test_ghz_to_mhz():
    assert ghz_to_mhz(4.7) == 4700
    assert ghz_to_mhz(None) is None


def test_parse_cpu():
    cpu = parse_cpu(RYZEN_9800X3D)
    assert cpu.id == "cpu-amd-ryzen-7-9800x3d"
    assert cpu.socket == "AM5"
    assert cpu.memory_types == [MemoryType.DDR5]
    assert cpu.tdp_w == 120
    assert cpu.base_clock_mhz == 4700
    assert cpu.boost_clock_mhz == 5200
    assert cpu.integrated_graphics is True
    assert cpu.includes_cooler is False
    assert cpu.threads is None


def test_parse_cpu_without_graphics_field():
    # F-серия: поля graphics нет вовсе
    record = {k: v for k, v in RYZEN_9800X3D.items() if k != "graphics"}
    assert parse_cpu(record).integrated_graphics is False


def test_parse_cpu_lga1700_supports_both_memory_types():
    cpu = parse_cpu({**RYZEN_9800X3D, "name": "Intel Core i5-13400F", "microarchitecture": "Raptor Lake"})
    assert cpu.socket == "LGA1700"
    assert cpu.memory_types == [MemoryType.DDR4, MemoryType.DDR5]


@pytest.mark.parametrize("name", [
    "AMD Threadripper 3990X",          # в датасете без слова Ryzen
    "AMD Ryzen Threadripper 7980X",
    "AMD EPYC 4564P",
])
def test_parse_cpu_rejects_workstation_lines(name):
    with pytest.raises(ValueError):
        parse_cpu({**RYZEN_9800X3D, "name": name})


def test_parse_cpu_rejects_unknown_architecture():
    with pytest.raises(ValueError):
        parse_cpu({**RYZEN_9800X3D, "microarchitecture": "Haswell"})


# --- Материнские платы -------------------------------------------------------------


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
    ("ASRock Z690 Steel Legend WiFi 6E/D5", "LGA1700", "Z690", MemoryType.DDR5),  # ASRock: /D5
    ("MSI MPG Z790I EDGE WIFI", "LGA1700", "Z790", MemoryType.DDR5),        # 700-я серия без пометки
])
def test_detect_memory_type(name, socket, chipset, expected):
    assert detect_memory_type(name, socket, chipset) == expected


@pytest.mark.parametrize("name, socket, chipset", [
    ("MSI MEG Z690I UNIFY", "LGA1700", "Z690"),   # 600-я серия без пометки — неоднозначно
    ("Biostar H610MH", "LGA1700", "H610"),        # то же
    ("Weird B650 Board DDR4", "AM5", "B650"),     # противоречие названия и сокета
])
def test_detect_memory_type_rejects(name, socket, chipset):
    with pytest.raises(ValueError):
        detect_memory_type(name, socket, chipset)


PRIME_B550M = {
    "name": "Asus PRIME B550M-A WIFI II", "price": 99.99, "socket": "AM4",
    "form_factor": "Micro ATX", "max_memory": 128, "memory_slots": 4,
    "color": "Blue / Silver",
}


def test_parse_motherboard():
    mb = parse_motherboard(PRIME_B550M)
    assert mb.id == "mb-asus-prime-b550m-a-wifi-ii"
    assert mb.socket == "AM4"
    assert mb.chipset == "B550"  # без M
    assert mb.form_factor == MotherBoardFormFactor.MICRO_ATX  # из "Micro ATX"
    assert mb.memory_type == MemoryType.DDR4  # по сокету
    assert mb.max_memory_gb == 128
    assert mb.memory_slots == 4
    assert mb.m2_slots is None  # неизвестно, а не 0
    assert mb.sata_ports is None


@pytest.mark.parametrize("override", [
    {"socket": "LGA1151"},                         # старый сокет
    {"form_factor": "SSI EEB"},                    # серверный форм-фактор
    {"name": "Asus PRIME B450M-A II"},             # 400-я серия AM4 — вне охвата
])
def test_parse_motherboard_rejects(override):
    with pytest.raises(ValueError):
        parse_motherboard({**PRIME_B550M, **override})


# --- Блоки питания -----------------------------------------------------------------

MAG_A750GL = {
    "name": "MSI MAG A750GL PCIE5", "price": 109.99, "type": "ATX",
    "efficiency": "gold", "wattage": 750, "modular": "Full", "color": "Black",
}


def test_parse_power_supply():
    psu = parse_power_supply(MAG_A750GL)
    assert psu.id == "psu-msi-mag-a750gl-pcie5-750w-atx-gold-full-black"
    assert psu.wattage_w == 750
    assert psu.form_factor == PsuFormFactor.ATX
    assert psu.efficiency == PsuEfficiency.GOLD
    assert psu.modularity == PsuModularity.FULL
    assert psu.has_12vhpwr is True  # из «PCIE5»
    assert psu.pcie_8pin is None  # неизвестно, а не 0


def test_parse_power_supply_non_modular_without_marker():
    psu = parse_power_supply({**MAG_A750GL, "name": "MSI MAG A650BN", "modular": False})
    assert psu.modularity == PsuModularity.NONE  # False из JSON → NONE
    assert psu.has_12vhpwr is None  # нет пометки — неизвестно, не False


def test_parse_power_supply_without_efficiency():
    psu = parse_power_supply({**MAG_A750GL, "efficiency": None})
    assert psu.efficiency is None


def test_parse_power_supply_detects_sfx_l():
    psu = parse_power_supply({**MAG_A750GL, "name": "SilverStone SX1000 SFX-L", "type": "SFX"})
    assert psu.form_factor == PsuFormFactor.SFX_L


def test_same_psu_name_different_wattage_gets_different_id():
    # В датасете «Thermaltake Smart» — это блоки на 430, 500, 600, 650, 700 Вт
    smart = {"name": "Thermaltake Smart", "type": "ATX", "efficiency": "plus", "modular": False, "color": None}
    a = parse_power_supply({**smart, "wattage": 500})
    b = parse_power_supply({**smart, "wattage": 600})
    assert a.id != b.id


def test_parse_power_supply_rejects_tfx():
    with pytest.raises(ValueError):
        parse_power_supply({**MAG_A750GL, "type": "TFX"})

SAPPHIRE_PULSE = {
    "name": "Sapphire PULSE", "price": 749.99, "chipset": "Radeon RX 9070 XT",
    "memory": 16, "core_clock": 2400, "boost_clock": 2970, "color": "Black", "length": 320,
}


def test_parse_gpu():
    gpu = parse_gpu(SAPPHIRE_PULSE)
    assert gpu.chipset == "Radeon RX 9070 XT"
    assert gpu.vram_gb == 16
    assert gpu.tdp_w == 304  # из справочника
    assert gpu.length_mm == 320
    assert gpu.power_connectors is None  # неизвестно, а не []


def test_same_gpu_name_different_chipset_gets_different_id():
    # «Sapphire PULSE» в датасете — и RX 9060 XT, и RX 9070 XT
    a = parse_gpu(SAPPHIRE_PULSE)
    b = parse_gpu({**SAPPHIRE_PULSE, "chipset": "Radeon RX 9060 XT", "length": 240})
    assert a.id != b.id


def test_parse_gpu_strips_lhr():
    gpu = parse_gpu({**SAPPHIRE_PULSE, "chipset": "GeForce RTX 3070 LHR"})
    assert gpu.chipset == "GeForce RTX 3070"


@pytest.mark.parametrize("override", [
    {"chipset": "GeForce GTX 1080"},    # вне охвата
    {"chipset": "Quadro RTX 4000"},     # профессиональная
    {"length": None},                    # без длины не проверить корпус
])
def test_parse_gpu_rejects(override):
    with pytest.raises(ValueError):
        parse_gpu({**SAPPHIRE_PULSE, **override})

SAMSUNG_990_PRO = {
    "name": "Samsung 990 Pro", "price": 149.99, "capacity": 2000, "price_per_gb": 0.075,
    "type": "SSD", "cache": 2048, "form_factor": "M.2-2280", "interface": "M.2 PCIe 4.0 X4",
}


def test_parse_storage_nvme_ssd():
    drive = parse_storage(SAMSUNG_990_PRO)
    assert drive.brand == "Samsung"
    assert drive.model == "990 Pro"
    assert drive.capacity_gb == 2000
    assert drive.media == StorageMedia.SSD
    assert drive.form_factor == StorageFormFactor.M2
    assert drive.interface == StorageInterface.NVME


def test_parse_storage_hdd():
    # У жёстких дисков в type — число оборотов, а 3.5 — число, не строка
    drive = parse_storage({
        **SAMSUNG_990_PRO, "name": "Seagate BarraCuda", "type": 7200,
        "form_factor": 3.5, "interface": "SATA 6.0 Gb/s",
    })
    assert drive.media == StorageMedia.HDD
    assert drive.form_factor == StorageFormFactor.INCH_3_5
    assert drive.interface == StorageInterface.SATA


def test_parse_storage_m2_sata():
    # M.2 по форме, но SATA по интерфейсу — займёт M.2-слот
    drive = parse_storage({**SAMSUNG_990_PRO, "interface": "M.2 SATA"})
    assert drive.form_factor == StorageFormFactor.M2
    assert drive.interface == StorageInterface.SATA


def test_same_drive_name_different_capacity_gets_different_id():
    a = parse_storage(SAMSUNG_990_PRO)
    b = parse_storage({**SAMSUNG_990_PRO, "capacity": 4000})
    assert a.id != b.id


def test_same_name_hdd_and_ssd_get_different_id():
    # «Western Digital Blue 1 ТБ 2.5"» в датасете — и жёсткий диск, и SSD
    wd_blue = {**SAMSUNG_990_PRO, "name": "Western Digital Blue", "capacity": 1000,
               "form_factor": 2.5, "interface": "SATA 6.0 Gb/s"}
    assert parse_storage({**wd_blue, "type": "SSD"}).id != parse_storage({**wd_blue, "type": 5400}).id


@pytest.mark.parametrize("override", [
    {"form_factor": "mSATA", "interface": "mSATA"},      # mSATA — не SATA, хоть и содержит «SATA»
    {"form_factor": "PCIe", "interface": "PCIe x4"},      # SSD-плата расширения
    {"form_factor": 2.5, "interface": "SAS 12.0 Gb/s"},   # серверный SAS
    {"type": None},                                        # тип неизвестен
])
def test_parse_storage_rejects(override):
    with pytest.raises(ValueError):
        parse_storage({**SAMSUNG_990_PRO, **override})