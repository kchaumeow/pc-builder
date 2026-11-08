"""Подбор под бюджет на настоящих данных.

Запуск из корня проекта:
    python scripts/budget_demo.py            # несколько бюджетов
    python scripts/budget_demo.py 1500       # один бюджет
    python scripts/budget_demo.py 1500 --work   # профиль «работа»
"""

import os
import sys
import time
from decimal import Decimal
from pathlib import Path

from pcbuilder.catalog import load_catalog
from pcbuilder.domain.models import Component
from pcbuilder.recommender.budget import best_build
from pcbuilder.recommender.scores import (
    GAMING,
    WORKSTATION,
    cpu_gaming_index,
    cpu_multicore_index,
    gpu_index,
)
from pcbuilder.recommender.solver import Requirements

DATASET = Path(os.environ.get("DOCYX_PATH", "~/projects/pc-part-dataset")).expanduser()
args = sys.argv[1:]
profile = WORKSTATION if "--work" in args else GAMING
budgets = [Decimal(a) for a in args if a != "--work"] or [
    Decimal(b) for b in ("800", "1200", "2000", "3000")
]

catalog = load_catalog(DATASET)
requirements = Requirements(min_ram_gb=32, min_storage_gb=1000)
print(f"Профиль: {profile.name}. Требования: {requirements.describe()}\n")

for budget in budgets:
    started = time.perf_counter()
    result = best_build(catalog, budget, profile, requirements)
    elapsed = time.perf_counter() - started

    print(f"=== Бюджет {budget} {catalog.currency}")
    if result is None:
        print("  ничего не нашлось\n")
        continue

    build = result.solution.build
    rows: list[tuple[str, Component | None]] = [
        ("CPU", build.cpu),
        ("Видеокарта", build.gpu),
        ("Плата", build.motherboard),
        ("Память", build.ram),
        ("Диск", build.storage[0]),
        ("БП", build.psu),
        ("Корпус", build.case),
        ("Кулер", build.cooling),
    ]
    for label, part in rows:
        if part is None:
            continue
        extra = ""
        if part is build.cpu:
            extra = f"игры {cpu_gaming_index(build.cpu)}, работа {cpu_multicore_index(build.cpu)}"
        elif part is build.gpu:
            extra = f"{build.gpu.chipset}, {gpu_index(build.gpu)}"
        print(f"  {label:11} {part.name:42} {extra:32} {catalog.price(part):>8}")
    print(f"  {'Итого':87} {result.solution.total:>8}")
    print(
        f"  общая оценка {result.score:.1f}; пар рассмотрено {result.pairs_considered}, "
        f"достроено {result.pairs_solved}; {elapsed:.1f} с\n"
    )
