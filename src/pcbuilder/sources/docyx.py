
from collections import Counter

from pcbuilder.domain.models import CPU, Component, RamKit, MemoryType
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