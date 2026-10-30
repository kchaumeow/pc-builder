
from collections import Counter

from pcbuilder.domain.models import CPU, Component, MotherBoardFormFactor, Motherboard, RamKit, MemoryType
import json
from collections.abc import Callable, Iterator
from pathlib import Path
import re


DDR_VERSIONS = {
    2: MemoryType.DDR2,
    3: MemoryType.DDR3,
    4: MemoryType.DDR4,
    5: MemoryType.DDR5,
}


def read_jsonl(path: Path) -> Iterator[dict]:
    with path.open(encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line:
                yield json.loads(line)


def load_parts[T: Component](
    path: Path,
    parse: Callable[[dict], T],
) -> tuple[dict[str, T], list[str]]:
    parts: dict[str, T] = {}
    errors: list[str] = []

    for record in read_jsonl(path):
        try:
            part = parse(record)
        except (KeyError, ValueError, TypeError) as e:
            errors.append(f"{record.get('name', '?')}: {e!r}")
            continue
        parts[part.id] = part

    return parts, errors

def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")

def memory_id(record: dict, ddr_version: int, speed_mhz: int, module_count: int, module_gb: int) -> str:
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
    name = record["name"].split(" ")
    module_count, module_gb = record["modules"]
    speed = record["speed"]
    if not isinstance(speed, list) or len(speed) != 2:
        raise ValueError(f"Unexpected speed format {speed!r} in {record['name']}")
    ddr_version, speed_mhz = record["speed"]

    memory_type = DDR_VERSIONS.get(ddr_version)
    if memory_type is None:
        raise ValueError(f"Unknown DDR version {ddr_version} in {record['name']}")


    return RamKit(brand=name[0], model=" ".join(name[1:]), modules=module_count, speed_mhz=speed_mhz, memory_type=memory_type, capacity_gb=module_count * module_gb, id=memory_id(record, ddr_version=ddr_version, speed_mhz=speed_mhz, module_count=module_count, module_gb=module_gb), cas_latency=record.get("cas_latency"))

CPU_ARCHITECTURES = {
    # AMD AM5
    "Zen 5": ("AM5", [MemoryType.DDR5]),
    "Zen 4": ("AM5", [MemoryType.DDR5]),
    # AMD AM4
    "Zen 3": ("AM4", [MemoryType.DDR4]),
    "Zen 2": ("AM4", [MemoryType.DDR4]),
    # Intel LGA1851
    "Arrow Lake": ("LGA1851", [MemoryType.DDR5]),
    # Intel LGA1700
    "Raptor Lake Refresh": ("LGA1700", [MemoryType.DDR4, MemoryType.DDR5]),
    "Raptor Lake": ("LGA1700", [MemoryType.DDR4, MemoryType.DDR5]),
    "Alder Lake": ("LGA1700", [MemoryType.DDR4, MemoryType.DDR5]),
}

EXCLUDED_LINES = ("Threadripper", "EPYC", "Xeon")

def parse_cpu(record: dict) -> CPU:
    name = record["name"].split(" ")

    if any(word in name for word in EXCLUDED_LINES):
        raise ValueError(f"Workstation/server CPU not supported: {name}")

    arch = record.get("microarchitecture")
    known = CPU_ARCHITECTURES.get(arch) # type: ignore
    if known is None:
        raise ValueError(f"Unknown microarchitecture {arch!r} in {record['name']}")
    socket, memory_types = known

    return CPU(brand=name[0], model=" ".join(name[1:]), socket=socket, tdp_w=record["tdp"], memory_types=memory_types, cores=record["core_count"], base_clock_mhz=record.get("core_clock"), boost_clock_mhz=record.get("boost_clock"), integrated_graphics=record.get("graphics") is not None, id="".join(name))

FORM_FACTORS = {
    "ATX": MotherBoardFormFactor.ATX,
    "Micro ATX": MotherBoardFormFactor.MICRO_ATX,
    "Mini ITX": MotherBoardFormFactor.MINI_ITX,
    "Thin Mini ITX": MotherBoardFormFactor.MINI_ITX,
    "EATX": MotherBoardFormFactor.E_ATX,
}

KNOWN_CHIPSETS = {
    # AM5
    "A620", "B650", "B650E", "X670", "X670E", "B840", "B850", "X870", "X870E",
    # AM4
    "A520", "B550", "X570",
    # LGA1700
    "H610", "B660", "H670", "Z690", "B760", "H770", "Z790",
    # LGA1851
    "H810", "B860", "Z890",
}

SOCKET_MEMORY_TYPES = {
    "AM5": MemoryType.DDR5,
    "AM4": MemoryType.DDR4,
    "LGA1851": MemoryType.DDR5,
}

CHIPSET_PATTERN = re.compile(r"(?<![A-Z0-9])([ABHQWXZ]\d{3}E?)(?!\d)")
SUPPORTED_SOCKETS = {"AM5", "AM4", "LGA1700", "LGA1851"}
NAME_MEMORY_PATTERN = re.compile(r"(?<![A-Z0-9])D(?:DR)?([45])(?![A-Z0-9])")
NAME_MEMORY_TYPES = {"4": MemoryType.DDR4, "5": MemoryType.DDR5}
# LGA1700, чипсеты 700-й серии: DDR5 — основная версия, DDR4-варианты помечены в названии.
# У 600-й серии этого соглашения нет (бывают DDR4-платы без пометки), поэтому её не включаем.
LGA1700_UNMARKED_DDR5_CHIPSETS = {"B760", "Z790", "H770"}

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
            raise ValueError(f"Name says {by_name}, socket {socket} implies {by_socket}: {name}")
        return by_name

    if by_socket is not None:
        return by_socket

    if socket == "LGA1700" and chipset in LGA1700_UNMARKED_DDR5_CHIPSETS:
        return MemoryType.DDR5

    raise ValueError(f"Cannot determine memory type for {socket}/{chipset} board: {name}")

def parse_motherboard(record: dict) -> Motherboard:
    name = record["name"]
    words = name.split(" ")
    socket = record["socket"]

    if socket not in SUPPORTED_SOCKETS:
        raise ValueError(f"Unsupported socket {socket}: {name}")

    form_factor = FORM_FACTORS.get(record["form_factor"])
    if form_factor is None:
        raise ValueError(f"Unknown form factor {record.get('form_factor')!r}: {name}")

    chipset = extract_chipset(name)
    if chipset is None or chipset not in KNOWN_CHIPSETS:
        raise ValueError(f"Unknown chipset {chipset!r}: {name}")

    return Motherboard(
        id=f"mb-{slugify(name)}",
        brand=words[0],
        model=" ".join(words[1:]),
        socket=socket,
        chipset=chipset,
        form_factor=form_factor,
        memory_type=detect_memory_type(name, socket, chipset),
        memory_slots=record["memory_slots"],
        max_memory_gb=record["max_memory"],
        # m2_slots и sata_ports в датасете нет — остаются None («неизвестно»)
    )