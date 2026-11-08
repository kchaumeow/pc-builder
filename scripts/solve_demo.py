"""Solver on real data: pick a CPU and a graphics card, get the rest.

Run from the project root:
    python scripts/solve_demo.py
"""

import os
import time
from pathlib import Path

from pcbuilder.catalog import load_catalog
from pcbuilder.domain.compatibility import estimated_power_w
from pcbuilder.domain.models import (
    CPU,
    GPU,
    Build,
    Component,
    ComponentType,
    Cooling,
    Motherboard,
    PowerSupply,
    RamKit,
    Storage,
)
from pcbuilder.recommender.solver import Requirements, Solver

DATASET = Path(os.environ.get("DOCYX_PATH", "~/projects/pc-part-dataset")).expanduser()


def details(part: Component) -> str:
    """Key specs of a part, to show what the solver picked."""
    match part:
        case CPU():
            return f"{part.socket}, {part.cores} cores"
        case Motherboard():
            return f"{part.chipset}, {part.form_factor}, {part.memory_type.upper()}"
        case RamKit():
            return f"{part.modules}×{part.capacity_gb // part.modules} GB {part.memory_type.upper()}-{part.speed_mhz}"
        case GPU():
            return f"{part.chipset}, {part.length_mm} mm"
        case Storage():
            return f"{part.capacity_gb} GB {part.kind}"
        case PowerSupply():
            return f"{part.wattage_w} W, {part.efficiency or 'no certification'}"
        case Cooling():
            return (
                f"tower {part.height_mm} mm"
                if part.height_mm
                else f"AIO {part.radiator_mm} mm"
            )
    return ""


catalog = load_catalog(DATASET)

cpu = catalog.find(ComponentType.CPU, "AMD Ryzen 5 7600")
# Cheapest RTX 4070 in the catalog (candidates are already sorted by price)
gpu = next(
    g
    for g in catalog.candidates(ComponentType.GPU)
    if isinstance(g, GPU) and g.chipset == "GeForce RTX 4070"
)

requirements = Requirements(min_ram_gb=32, min_storage_gb=1000)
solver = Solver(catalog, requirements)

started = time.perf_counter()
solution = solver.complete(Build(cpu=cpu, gpu=gpu))
elapsed = time.perf_counter() - started

if solution is None:
    print("No compatible build found")
    raise SystemExit(1)

build = solution.build
print(f"Requirements: {requirements.describe()}\n")
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
    if part is None:
        continue
    print(
        f"  {label:14} {part.name:40} {details(part):30} {catalog.price(part):>8} {catalog.currency}"
    )
print(f"  {'Total':86} {solution.total:>8} {catalog.currency}")

print(f"\nPower draw ~{estimated_power_w(build)} W")
print(f"Part checks: {solution.steps}, search time: {elapsed:.2f} s")
for issue in solution.issues:
    print(f"  [{issue.severity}] {issue.rule}: {issue.message}")
