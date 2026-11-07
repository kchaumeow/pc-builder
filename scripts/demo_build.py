"""Первая сборка из настоящих данных: детали из датасета docyx + корпуса и кулеры из data/seeds.

Детали выбираются простыми фильтрами — это ещё не подбор, а проверка, что все части
проекта работают вместе. Подбор под бюджет — следующий шаг (солвер).

Запуск из корня проекта:
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

DATASET = Path(os.environ.get("DOCYX_PATH", "~/projects/pc-part-dataset")).expanduser() / "data" / "jsonl"


def first[T: Component](parts: Iterable[T], condition: Callable[[T], bool]) -> T:
    for part in parts:
        if condition(part):
            return part
    raise LookupError("Ни одна деталь не подошла под условие")


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
    motherboard=first(boards.values(), lambda b: b.chipset == "B650" and b.form_factor == "ATX"),
    ram=first(memory.values(), lambda r: r.memory_type == MemoryType.DDR5 and r.capacity_gb == 32
              and r.modules == 2 and r.speed_mhz == 6000),
    gpu=first(gpus.values(), lambda g: g.chipset == "GeForce RTX 4070" and g.length_mm <= 300),
    storage=[first(drives.values(), lambda d: d.name == "Samsung 990 Pro" and d.capacity_gb == 2000)],
    psu=first(psus.values(), lambda p: p.wattage_w == 750 and p.efficiency == "80 Plus Gold"),
    case=cases["case-fractal-design-north"],
    cooling=coolers["cooler-thermalright-peerless-assassin-120-se"],
)

print("Сборка:")
for label, part in [("CPU", build.cpu), ("Плата", build.motherboard), ("Память", build.ram),
                    ("Видеокарта", build.gpu), ("Диск", build.storage[0]), ("БП", build.psu),
                    ("Корпус", build.case), ("Кулер", build.cooling)]:
    print(f"  {label:11} {part.name}")

print(f"\nОценка потребления: {estimated_power_w(build)} Вт")

issues = check(build, complete=True)
print(f"\nПроверка: {len(issues)} замечаний")
for issue in issues:
    print(f"  [{issue.severity}] {issue.rule}: {issue.message}")
if not issues:
    print("  Совместимо ✓")