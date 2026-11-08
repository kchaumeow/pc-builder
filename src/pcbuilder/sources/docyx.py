"""Loader for the docyx/pc-part-dataset dataset (a PCPartPicker snapshot in JSON Lines).

Each parse_* function turns one dataset record into our model.
If a record cannot be parsed reliably, it raises ValueError with a clear reason:
better to skip a part than to load it with wrong data.
"""

import json
import re
from collections.abc import Callable, Iterator, Mapping
from decimal import Decimal
from pathlib import Path

from pcbuilder.domain.models import (
    CPU,
    GPU,
    Component,
    MemoryType,
    Motherboard,
    MotherBoardFormFactor,
    Offer,
    PowerSupply,
    PsuEfficiency,
    PsuFormFactor,
    PsuModularity,
    RamKit,
    Storage,
    StorageFormFactor,
    StorageInterface,
    StorageMedia,
)

# --- Common ------------------------------------------------------------------------


def read_jsonl(path: Path) -> Iterator[dict]:
    """Read JSONL line by line: one line is one record."""
    with path.open(encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line:
                yield json.loads(line)


def load_parts[T: Component](
    path: Path,
    parse: Callable[[dict], T],
) -> tuple[dict[str, T], list[str]]:
    """Load a whole file. Returns (parts by id, list of rejections with reasons).

    Only KeyError (missing required field) and ValueError (our deliberate rejection
    or a pydantic validation error) are caught. Anything else is a bug; let it fail loudly.
    """
    parts: dict[str, T] = {}
    errors: list[str] = []

    for record in read_jsonl(path):
        try:
            part = parse(record)
        except (KeyError, ValueError) as e:
            errors.append(f"{record.get('name', '?')}: {e!r}")
            continue

        existing = parts.get(part.id)
        if existing is not None and existing != part:
            errors.append(f"{part.id}: conflicting records with the same id")
            continue
        parts[part.id] = part

    return parts, errors


def slugify(text: str) -> str:
    text = text.replace("+", " plus ")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def split_brand(name: str) -> tuple[str, str]:
    """First word is the brand, the rest is the model. Does not work for multi-word brands."""
    words = name.split(" ")
    return words[0], " ".join(words[1:])


def require_pair(record: dict, field: str) -> tuple[int, int]:
    """A pair field like [5, 6000]. Otherwise ValueError rather than TypeError on unpacking."""
    value = record[field]
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"Unexpected {field} format {value!r} in {record['name']}")
    return value[0], value[1]


# --- Memory ------------------------------------------------------------------------

DDR_VERSIONS = {
    2: MemoryType.DDR2,
    3: MemoryType.DDR3,
    4: MemoryType.DDR4,
    5: MemoryType.DDR5,
}


def memory_id(
    record: dict, ddr_version: int, speed_mhz: int, module_count: int, module_gb: int
) -> str:
    # The dataset name is a series and capacity, not a product: many kits share one name.
    # So the identity is built from the specs.
    parts = [
        record["name"],
        f"ddr{ddr_version}",
        str(speed_mhz),
        f"{module_count}x{module_gb}",
        f"cl{record.get('cas_latency')}",
        record.get("color") or "",
    ]
    return "ram-" + slugify(" ".join(parts))


def parse_memory(record: dict) -> RamKit:
    name = record["name"]
    ddr_version, speed_mhz = require_pair(record, "speed")
    module_count, module_gb = require_pair(record, "modules")

    memory_type = DDR_VERSIONS.get(ddr_version)
    if memory_type is None:
        raise ValueError(f"Unknown DDR version {ddr_version} in {name}")

    brand, model = split_brand(name)
    return RamKit(
        id=memory_id(record, ddr_version, speed_mhz, module_count, module_gb),
        brand=brand,
        model=model,
        memory_type=memory_type,
        speed_mhz=speed_mhz,
        modules=module_count,
        capacity_gb=module_count * module_gb,  # the dataset gives per-module capacity
        cas_latency=record.get("cas_latency"),
    )


# --- CPUs --------------------------------------------------------------------------

# Microarchitecture -> (socket, memory types). The dataset has no socket, so we infer it.
# Scope: only platforms where the socket reliably determines compatibility.
# Zen/Zen+ are excluded: B550 boards do not officially support them.
CPU_ARCHITECTURES = {
    "Zen 5": ("AM5", [MemoryType.DDR5]),
    "Zen 4": ("AM5", [MemoryType.DDR5]),
    "Zen 3": ("AM4", [MemoryType.DDR4]),
    "Zen 2": ("AM4", [MemoryType.DDR4]),
    "Arrow Lake": ("LGA1851", [MemoryType.DDR5]),
    "Raptor Lake Refresh": ("LGA1700", [MemoryType.DDR4, MemoryType.DDR5]),
    "Raptor Lake": ("LGA1700", [MemoryType.DDR4, MemoryType.DDR5]),
    "Alder Lake": ("LGA1700", [MemoryType.DDR4, MemoryType.DDR5]),
}

# Same architecture but a different socket: the lookup table would give a wrong answer.
EXCLUDED_LINES = ("Threadripper", "EPYC", "Xeon")


def ghz_to_mhz(value: float | None) -> int | None:
    if value is None:
        return None
    return round(value * 1000)  # round, not int: 4.7 * 1000 can be 4699.999...


def parse_cpu(record: dict) -> CPU:
    name = record["name"]

    if any(line in name for line in EXCLUDED_LINES):
        raise ValueError(f"Workstation/server CPU not supported: {name}")

    arch = record.get("microarchitecture")
    if arch is None or arch not in CPU_ARCHITECTURES:
        raise ValueError(f"Unknown microarchitecture {arch!r} in {name}")
    socket, memory_types = CPU_ARCHITECTURES[arch]

    brand, model = split_brand(name)
    return CPU(
        id=f"cpu-{slugify(name)}",
        brand=brand,
        model=model,
        socket=socket,
        memory_types=memory_types,
        tdp_w=record["tdp"],
        cores=record["core_count"],
        architecture=arch,
        base_clock_mhz=ghz_to_mhz(record.get("core_clock")),
        boost_clock_mhz=ghz_to_mhz(record.get("boost_clock")),
        integrated_graphics=record.get("graphics") is not None,
        includes_cooler=False,  # not in the dataset; False is safer, it asks for a cooler
    )


# --- Motherboards ------------------------------------------------------------------

SUPPORTED_SOCKETS = {"AM5", "AM4", "LGA1700", "LGA1851"}

FORM_FACTORS = {
    "ATX": MotherBoardFormFactor.ATX,
    "Micro ATX": MotherBoardFormFactor.MICRO_ATX,
    "Mini ITX": MotherBoardFormFactor.MINI_ITX,
    "Thin Mini ITX": MotherBoardFormFactor.MINI_ITX,  # same 170x170 size, low profile
    "EATX": MotherBoardFormFactor.E_ATX,
}

KNOWN_CHIPSETS = {
    "A620",
    "B650",
    "B650E",
    "X670",
    "X670E",
    "B840",
    "B850",
    "X870",
    "X870E",  # AM5
    "A520",
    "B550",
    "X570",  # AM4, 500 series
    "H610",
    "B660",
    "H670",
    "Z690",
    "B760",
    "H770",
    "Z790",  # LGA1700
    "H810",
    "B860",
    "Z890",  # LGA1851
}

# Sockets with a single memory type. LGA1700 is left out on purpose: it has both DDR4 and DDR5.
SOCKET_MEMORY_TYPES = {
    "AM5": MemoryType.DDR5,
    "AM4": MemoryType.DDR4,
    "LGA1851": MemoryType.DDR5,
}

# LGA1700, 700 series: DDR5 is the main version, DDR4 variants are marked in the name.
# The 600 series has no such convention (some DDR4 boards are unmarked), so it is excluded.
LGA1700_UNMARKED_DDR5_CHIPSETS = {"B760", "Z790", "H770"}

# A letter + 3 digits + an optional E. Anything but a digit may follow
# (B550M, B760I, Z790ITX, B660GTA). The regex finds candidates, KNOWN_CHIPSETS decides.
CHIPSET_PATTERN = re.compile(r"(?<![A-Z0-9])([ABHQWXZ]\d{3}E?)(?!\d)")

# "DDR4", "D4" (ASUS), "/D5" (ASRock)
NAME_MEMORY_PATTERN = re.compile(r"(?<![A-Z0-9])D(?:DR)?([45])(?![A-Z0-9])")
NAME_MEMORY_TYPES = {"4": MemoryType.DDR4, "5": MemoryType.DDR5}


def extract_chipset(name: str) -> str | None:
    match = CHIPSET_PATTERN.search(name.upper())
    if match is None:
        return None
    return match.group(1)


def detect_memory_type(name: str, socket: str, chipset: str) -> MemoryType:
    by_socket = SOCKET_MEMORY_TYPES.get(socket)

    match = NAME_MEMORY_PATTERN.search(name.upper())
    if match is not None:
        by_name = NAME_MEMORY_TYPES[match.group(1)]
        if by_socket is not None and by_name != by_socket:
            raise ValueError(
                f"Name says {by_name}, socket {socket} implies {by_socket}: {name}"
            )
        return by_name

    if by_socket is not None:
        return by_socket

    if socket == "LGA1700" and chipset in LGA1700_UNMARKED_DDR5_CHIPSETS:
        return MemoryType.DDR5

    raise ValueError(
        f"Cannot determine memory type for {socket}/{chipset} board: {name}"
    )


def parse_motherboard(record: dict) -> Motherboard:
    name = record["name"]
    socket = record["socket"]

    if socket not in SUPPORTED_SOCKETS:
        raise ValueError(f"Unsupported socket {socket}: {name}")

    raw_form_factor = record.get("form_factor")
    if raw_form_factor is None or raw_form_factor not in FORM_FACTORS:
        raise ValueError(f"Unknown form factor {raw_form_factor!r}: {name}")

    chipset = extract_chipset(name)
    if chipset is None or chipset not in KNOWN_CHIPSETS:
        raise ValueError(f"Unknown chipset {chipset!r}: {name}")

    brand, model = split_brand(name)
    return Motherboard(
        id=f"mb-{slugify(name)}",
        brand=brand,
        model=model,
        socket=socket,
        chipset=chipset,
        form_factor=FORM_FACTORS[raw_form_factor],
        memory_type=detect_memory_type(name, socket, chipset),
        memory_slots=record["memory_slots"],
        max_memory_gb=record["max_memory"],
        # m2_slots and sata_ports are not in the dataset and stay None ("unknown")
    )


# --- Power supplies ----------------------------------------------------------------

# TFX, Flex ATX and pico PSUs are not loaded: cases cannot accept them yet.
PSU_FORM_FACTORS = {
    "ATX": PsuFormFactor.ATX,
    "SFX": PsuFormFactor.SFX,
}

EFFICIENCY = {
    "plus": PsuEfficiency.PLUS,
    "bronze": PsuEfficiency.BRONZE,
    "silver": PsuEfficiency.SILVER,
    "gold": PsuEfficiency.GOLD,
    "platinum": PsuEfficiency.PLATINUM,
    "titanium": PsuEfficiency.TITANIUM,
}

# The dataset mixes strings and booleans in one field: "Full", "Semi", false
MODULARITY = {
    "Full": PsuModularity.FULL,
    "Full / Side": PsuModularity.FULL,
    "Semi": PsuModularity.SEMI,
    False: PsuModularity.NONE,
}

# ATX 3.x power supplies always have a native 12VHPWR (12V-2x6)
NATIVE_12VHPWR_MARKERS = ("PCIE5", "ATX 3")


def detect_psu_form_factor(record: dict) -> PsuFormFactor:
    raw = record.get("type")
    if raw is None or raw not in PSU_FORM_FACTORS:
        raise ValueError(f"Unsupported PSU form factor {raw!r}: {record['name']}")
    form_factor = PSU_FORM_FACTORS[raw]
    # The dataset records SFX-L as SFX, so tell them apart by name
    if form_factor == PsuFormFactor.SFX and "SFX-L" in record["name"].upper():
        return PsuFormFactor.SFX_L
    return form_factor


def detect_12vhpwr(name: str) -> bool | None:
    if any(marker in name.upper() for marker in NATIVE_12VHPWR_MARKERS):
        return True
    return None  # no marker is not proof that the cable is missing


def psu_id(record: dict) -> str:
    # As with memory: the name is a series ("Thermaltake Smart") covering units of
    # different wattage and certification. The identity is built from the specs.
    parts = [
        record["name"],
        f"{record['wattage']}w",
        record.get("type") or "",
        record.get("efficiency") or "",
        str(record.get("modular")),
        record.get("color") or "",
    ]
    return "psu-" + slugify(" ".join(parts))


def parse_power_supply(record: dict) -> PowerSupply:
    name = record["name"]
    brand, model = split_brand(name)

    efficiency = record.get("efficiency")
    modular = record.get("modular")

    return PowerSupply(
        id=psu_id(record),
        brand=brand,
        model=model,
        wattage_w=record["wattage"],
        form_factor=detect_psu_form_factor(record),
        efficiency=EFFICIENCY.get(efficiency) if efficiency is not None else None,
        modularity=MODULARITY.get(modular) if modular is not None else None,
        has_12vhpwr=detect_12vhpwr(name),
        # pcie_8pin and length_mm are not in the dataset and stay None
    )


# --- Graphics cards ----------------------------------------------------------------

# Chipset -> reference power (Total Board Power), W. The dataset has no TDP, so we infer it.
# Keys match the dataset exactly. Memory size in the key matters: the RTX 3050 6GB and 8GB
# differ in power by almost 2x. Power connectors cannot be inferred from this:
# the card maker chooses them, not NVIDIA/AMD.
# Scope: generations sold new. Pro cards (Quadro, RTX Ada, Arc Pro) are excluded.
GPU_TDP_W = {
    # NVIDIA RTX 30
    "GeForce RTX 3050 6GB": 70,
    "GeForce RTX 3050 8GB": 130,
    "GeForce RTX 3060 8GB": 170,
    "GeForce RTX 3060 12GB": 170,
    "GeForce RTX 3060 Ti": 200,
    "GeForce RTX 3070": 220,
    "GeForce RTX 3070 Ti": 290,
    "GeForce RTX 3080 10GB": 320,
    "GeForce RTX 3080 12GB": 350,
    "GeForce RTX 3080 Ti": 350,
    "GeForce RTX 3090": 350,
    "GeForce RTX 3090 Ti": 450,
    # NVIDIA RTX 40
    "GeForce RTX 4060": 115,
    "GeForce RTX 4060 Ti": 165,  # 8GB: 160, 16GB: 165; the dataset does not distinguish them, take the higher
    "GeForce RTX 4070": 200,
    "GeForce RTX 4070 SUPER": 220,
    "GeForce RTX 4070 Ti": 285,
    "GeForce RTX 4070 Ti SUPER": 285,
    "GeForce RTX 4080": 320,
    "GeForce RTX 4080 SUPER": 320,
    "GeForce RTX 4090": 450,
    # NVIDIA RTX 50
    "GeForce RTX 5050": 130,
    "GeForce RTX 5060": 145,
    "GeForce RTX 5060 Ti": 180,
    "GeForce RTX 5070": 250,
    "GeForce RTX 5070 Ti": 300,
    "GeForce RTX 5080": 360,
    "GeForce RTX 5090": 575,
    # AMD RX 6000
    "Radeon RX 6400": 53,
    "Radeon RX 6500 XT": 107,
    "Radeon RX 6600": 132,
    "Radeon RX 6600 XT": 160,
    "Radeon RX 6650 XT": 180,
    "Radeon RX 6700": 175,
    "Radeon RX 6700 XT": 230,
    "Radeon RX 6750 XT": 250,
    "Radeon RX 6800": 250,
    "Radeon RX 6800 XT": 300,
    "Radeon RX 6900 XT": 300,
    "Radeon RX 6950 XT": 335,
    # AMD RX 7000
    "Radeon RX 7600": 165,
    "Radeon RX 7600 XT": 190,
    "Radeon RX 7700 XT": 245,
    "Radeon RX 7800 XT": 263,
    "Radeon RX 7900 GRE": 260,
    "Radeon RX 7900 XT": 315,
    "Radeon RX 7900 XTX": 355,
    # AMD RX 9000
    "Radeon RX 9060 XT": 160,  # 8GB: 150, 16GB: 160; take the higher
    "Radeon RX 9070": 220,
    "Radeon RX 9070 XT": 304,
    # Intel Arc
    "Arc A310": 75,
    "Arc A380": 75,
    "Arc A580": 185,
    "Arc A750": 225,
    "Arc A770": 225,
    "Arc B570": 150,
    "Arc B580": 190,
}


def normalize_gpu_chipset(chipset: str) -> str:
    """LHR is the mining-limited version; power is the same, so drop the suffix."""
    return chipset.removesuffix(" LHR")


def gpu_id(record: dict, chipset: str) -> str:
    # The name is the maker's product line ("Sapphire PULSE"), often without the chip.
    parts = [
        record["name"],
        chipset,
        f"{record['memory']}gb",
        f"{record['length']}mm",
        record.get("color") or "",
    ]
    return "gpu-" + slugify(" ".join(parts))


def parse_gpu(record: dict) -> GPU:
    name = record["name"]
    raw_chipset = record.get("chipset")
    if raw_chipset is None:
        raise ValueError(f"Unknown GPU chipset None: {name}")

    chipset = normalize_gpu_chipset(raw_chipset)
    if chipset not in GPU_TDP_W:
        raise ValueError(f"Unknown GPU chipset {raw_chipset!r}: {name}")

    if record.get("length") is None:
        raise ValueError(f"GPU length unknown: {name}")

    brand, model = split_brand(name)
    return GPU(
        id=gpu_id(record, chipset),
        brand=brand,
        model=model,
        chipset=chipset,
        vram_gb=record["memory"],
        tdp_w=GPU_TDP_W[chipset],
        length_mm=record["length"],
        # power_connectors and recommended_psu_w are not in the dataset and stay None
    )


# --- Storage -----------------------------------------------------------------------

# In the dataset 2.5 and 3.5 are numbers, while M.2 is a string like "M.2-2280". All M.2
# lengths are the same to us: the rule counts slots, not length. mSATA and PCIe cards are out of scope.
STORAGE_INCH_FORM_FACTORS = {
    2.5: StorageFormFactor.INCH_2_5,
    3.5: StorageFormFactor.INCH_3_5,
}


def detect_storage_form_factor(record: dict) -> StorageFormFactor:
    value = record.get("form_factor")
    if isinstance(value, (int, float)) and value in STORAGE_INCH_FORM_FACTORS:
        return STORAGE_INCH_FORM_FACTORS[value]
    if isinstance(value, str) and value.startswith("M.2"):
        return StorageFormFactor.M2
    raise ValueError(f"Unsupported storage form factor {value!r}: {record['name']}")


def detect_storage_interface(record: dict) -> StorageInterface:
    # Check the start of the string, not a substring, otherwise "mSATA" passes as SATA.
    # Out of scope: mSATA, SAS, U.2, PATA and PCIe cards ("PCIe x4", no leading "M.2").
    value = record.get("interface")
    if isinstance(value, str):
        if value.startswith("M.2 PCIe"):
            return StorageInterface.NVME
        if value == "M.2 SATA" or value.startswith("SATA"):
            return StorageInterface.SATA
    raise ValueError(f"Unsupported storage interface {value!r}: {record['name']}")


def detect_storage_media(record: dict) -> StorageMedia:
    # "SSD" is a string; hard drives have an RPM number instead (7200, 5400...)
    value = record.get("type")
    if value == "SSD":
        return StorageMedia.SSD
    if isinstance(value, int):
        return StorageMedia.HDD
    raise ValueError(f"Unknown storage type {value!r}: {record['name']}")


def storage_id(record: dict) -> str:
    # The name is the model ("Samsung 990 Pro"); each capacity is a separate product.
    # The type is needed too: "Western Digital Blue" is both an HDD and an SSD line.
    parts = [
        record["name"],
        str(record.get("type")),
        f"{record['capacity']}gb",
        str(record.get("form_factor")),
        record.get("interface") or "",
    ]
    return "storage-" + slugify(" ".join(parts))


def parse_storage(record: dict) -> Storage:
    name = record["name"]
    brand, model = split_brand(name)
    return Storage(
        id=storage_id(record),
        brand=brand,
        model=model,
        capacity_gb=record["capacity"],
        media=detect_storage_media(record),
        form_factor=detect_storage_form_factor(record),
        interface=detect_storage_interface(record),
    )


# --- Prices ------------------------------------------------------------------------

SOURCE = "docyx"
CURRENCY = "USD"  # the dataset is a snapshot of US PCPartPicker


def to_price(value: float | None) -> Decimal | None:
    if value is None:
        return None

    return Decimal(str(value))


def keep_cheaper(offers: dict[str, Offer], offer: Offer) -> None:
    existing = offers.get(offer.part_id)
    if existing is None or offer.price < existing.price:
        offers[offer.part_id] = offer


def load_offers(path: Path, parse: Callable[[dict], Component]) -> dict[str, Offer]:
    """Prices for the parts that parse loads, keyed by part id.

    The same part appears in the dataset several times with different prices;
    the lowest is kept. Records without a price or rejected by parse are skipped.
    """
    offers: dict[str, Offer] = {}
    for record in read_jsonl(path):
        price = to_price(record.get("price"))
        if price is None:
            continue
        try:
            part = parse(record)
        except (KeyError, ValueError):
            continue
        keep_cheaper(
            offers,
            Offer(part_id=part.id, source=SOURCE, price=price, currency=CURRENCY),
        )
    return offers


def load_offers_by_name(path: Path, parts: Mapping[str, Component]) -> dict[str, Offer]:
    """Prices for parts from another source (seed files), matched by name.

    Matching is case-insensitive: the dataset has "Lian Li LANCOOL 216", we have "Lian Li Lancool 216".
    """
    by_name: dict[str, list[str]] = {}
    for part in parts.values():
        by_name.setdefault(part.name.lower(), []).append(part.id)

    offers: dict[str, Offer] = {}
    for record in read_jsonl(path):
        price = to_price(record.get("price"))
        if price is None:
            continue
        for part_id in by_name.get(record["name"].lower(), []):
            keep_cheaper(
                offers,
                Offer(part_id=part_id, source=SOURCE, price=price, currency=CURRENCY),
            )
    return offers
