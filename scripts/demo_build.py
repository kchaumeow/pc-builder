"""First build from real data: parts from the docyx dataset + cases and coolers from data/seeds.

Parts are picked with simple filters — this isn't a recommender yet, just a check that all
parts of the project work together. Budget-based picking is the next step (the solver).

Run from the project root:
    python scripts/demo_build.py
"""

import os
from collections.abc import Callable, Iterable
from pathlib import Path

from pcbuilder.domain.compatibility import check, estimated_power_w
from pcbuilder.domain.models import Build, Component, MemoryType
from pcbuilder.sources.docyx import (
    load_parts,
    parse_cpu,
    parse_gpu,
    parse_memory,
    parse_motherboard,
    parse_power_supply,
    parse_storage,
)
from pcbuilder.sources.seeds import load_cases, load_coolers

DATASET = (
    Path(os.environ.get("DOCYX_PATH", "~/projects/pc-part-dataset")).expanduser()
    / "data"
    / "jsonl"
)


def first[T: Component](parts: Iterable[T], condition: Callable[[T], bool]) -> T:
    for part in parts:
        if condition(part):
            return part
    raise LookupError("No part matched the condition")


cpus, _ = load_parts(DATASET / "cpu.jsonl", parse_cpu)
boards, _ = load_parts(DATASET / "motherboard.jsonl", parse_motherboard)
memory, _ = load_parts(DATASET / "memory.jsonl", parse_memory)
gpus, _ = load_parts(DATASET / "video-card.jsonl", parse_gpu)
psus, _ = load_parts(DATASET / "power-supply.jsonl", parse_power_supply)
drives, _ = load_parts(DATASET / "internal-hard-drive.jsonl", parse_storage)
cases = load_cases()
coolers = load_coolers()

build = Build(
    cpu=first(cpus.values(), lambda c: c.name == "AMD Ryzen 5 7600"),
    motherboard=first(
        boards.values(), lambda b: b.chipset == "B650" and b.form_factor == "ATX"
    ),
    ram=first(
        memory.values(),
        lambda r: (
            r.memory_type == MemoryType.DDR5
            and r.capacity_gb == 32
            and r.modules == 2
            and r.speed_mhz == 6000
        ),
    ),
    gpu=first(
        gpus.values(), lambda g: g.chipset == "GeForce RTX 4070" and g.length_mm <= 300
    ),
    storage=[
        first(
            drives.values(),
            lambda d: d.name == "Samsung 990 Pro" and d.capacity_gb == 2000,
        )
    ],
    psu=first(
        psus.values(), lambda p: p.wattage_w == 750 and p.efficiency == "80 Plus Gold"
    ),
    case=cases["case-fractal-design-north"],
    cooling=coolers["cooler-thermalright-peerless-assassin-120-se"],
)

print("Build:")
for label, part in [
    ("CPU", build.cpu),
    ("Motherboard", build.motherboard),
    ("Memory", build.ram),
    ("Graphics card", build.gpu),
    ("Storage", build.storage[0]),
    ("Power supply", build.psu),
    ("Case", build.case),
    ("CPU cooler", build.cooling),
]:
    print(f"  {label:14} {part.name}")

print(f"\nEstimated power draw: {estimated_power_w(build)} W")

issues = check(build, complete=True)
print(f"\nCheck: {len(issues)} issues")
for issue in issues:
    print(f"  [{issue.severity}] {issue.rule}: {issue.message}")
if not issues:
    print("  Compatible ✓")
