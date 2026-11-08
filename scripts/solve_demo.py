"""Солвер на настоящих данных: задаём процессор и видеокарту — получаем остальное.

Запуск из корня проекта:
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
    """Главные характеристики детали — чтобы было видно, что выбрал солвер."""
    match part:
        case CPU():
            return f"{part.socket}, {part.cores} ядер"
        case Motherboard():
            return f"{part.chipset}, {part.form_factor}, {part.memory_type.upper()}"
        case RamKit():
            return f"{part.modules}×{part.capacity_gb // part.modules} ГБ {part.memory_type.upper()}-{part.speed_mhz}"
        case GPU():
            return f"{part.chipset}, {part.length_mm} мм"
        case Storage():
            return f"{part.capacity_gb} ГБ {part.kind}"
        case PowerSupply():
            return f"{part.wattage_w} Вт, {part.efficiency or 'без сертификата'}"
        case Cooling():
            return (
                f"башня {part.height_mm} мм"
                if part.height_mm
                else f"водянка {part.radiator_mm} мм"
            )
    return ""


catalog = load_catalog(DATASET)

cpu = catalog.find(ComponentType.CPU, "AMD Ryzen 5 7600")
# Самая дешёвая RTX 4070 в каталоге (кандидаты уже отсортированы по цене)
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
    print("Совместимой сборки не нашлось")
    raise SystemExit(1)

build = solution.build
print(f"Требования: {requirements.describe()}\n")
for label, part in [
    ("CPU", build.cpu),
    ("Плата", build.motherboard),
    ("Память", build.ram),
    ("Видеокарта", build.gpu),
    ("Диск", build.storage[0]),
    ("БП", build.psu),
    ("Корпус", build.case),
    ("Кулер", build.cooling),
]:
    if part is None:
        continue
    print(
        f"  {label:11} {part.name:40} {details(part):30} {catalog.price(part):>8} {catalog.currency}"
    )
print(f"  {'Итого':83} {solution.total:>8} {catalog.currency}")

print(f"\nПотребление ~{estimated_power_w(build)} Вт")
print(f"Проверок деталей: {solution.steps}, время поиска: {elapsed:.2f} с")
for issue in solution.issues:
    print(f"  [{issue.severity}] {issue.rule}: {issue.message}")
