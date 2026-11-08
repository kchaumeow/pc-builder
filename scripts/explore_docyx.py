"""Разведка датасета docyx и проверка загрузчиков.

Для каждой категории два шага:
  1. Сырые записи: сколько всего, сколько без важных полей, какие значения встречаются.
     Работает всегда — даже для категорий, у которых ещё нет загрузчика.
  2. Загрузчик (если он уже написан): сколько загрузилось, сколько отказов,
     и есть ли среди отказов неожиданные — то есть не из списка осознанных причин.

Запуск из корня проекта:
    python scripts/explore_docyx.py                    # все категории
    python scripts/explore_docyx.py video-card         # одна категория
    python scripts/explore_docyx.py cpu memory         # несколько

Путь к датасету — переменная окружения DOCYX_PATH или ~/projects/pc-part-dataset.
"""

import os
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from pcbuilder.sources.docyx import (
    load_parts,
    parse_cpu,
    parse_gpu,
    parse_memory,
    parse_motherboard,
    parse_power_supply,
    parse_storage,
    read_jsonl,
)


class Category(BaseModel):
    parse: Callable | None = None  # None — загрузчика пока нет
    expected_reasons: tuple[str, ...] = ()  # осознанные причины отказа
    count_fields: tuple[str, ...] = ()  # поля, значения которых посчитать
    required_fields: tuple[str, ...] = ()  # поля, отсутствие которых важно увидеть
    top: int = 15  # сколько самых частых значений показывать


CATEGORIES: dict[str, Category] = {
    "memory": Category(
        parse=parse_memory,
        expected_reasons=("Unknown DDR version", "Unexpected speed format"),
        required_fields=("speed", "modules", "cas_latency"),
    ),
    "cpu": Category(
        parse=parse_cpu,
        expected_reasons=("Unknown microarchitecture", "not supported"),
        count_fields=("microarchitecture",),
        required_fields=("tdp", "graphics"),
        top=40,
    ),
    "motherboard": Category(
        parse=parse_motherboard,
        expected_reasons=(
            "Unsupported socket",
            "Unknown form factor",
            "Unknown chipset",
            "Cannot determine memory type",
        ),
        count_fields=("socket", "form_factor"),
    ),
    "power-supply": Category(
        parse=parse_power_supply,
        expected_reasons=("Unsupported PSU form factor",),
        count_fields=("type", "efficiency", "modular"),
    ),
    "video-card": Category(
        parse=parse_gpu,
        expected_reasons=("Unknown GPU chipset", "GPU length unknown"),
        count_fields=("chipset",),
        required_fields=("length", "memory"),
        top=60,
    ),
    "case": Category(
        count_fields=("type", "side_panel"),
        required_fields=("psu",),
    ),
    "cpu-cooler": Category(
        count_fields=("size",),
        required_fields=("size",),
    ),
    "internal-hard-drive": Category(
        parse=parse_storage,
        expected_reasons=(
            "Unsupported storage form factor",
            "Unsupported storage interface",
            "Unknown storage type",
        ),
        count_fields=("type", "form_factor", "interface"),
    ),
}


def explore_raw(records: list[dict], category: Category) -> None:
    print(f"  записей: {len(records)}")
    for name in category.required_fields:
        missing = sum(1 for r in records if r.get(name) is None)
        print(f"  без поля «{name}»: {missing}")

    for name in category.count_fields:
        counts = Counter(r.get(name) for r in records)
        print(f"\n  «{name}» — {len(counts)} разных значений, самые частые:")
        for value, count in counts.most_common(category.top):
            print(f"    {count:6}  {value!r}")


def explore_loader(path: Path, records: list[dict], category: Category) -> None:
    parts, errors = load_parts(path, category.parse)
    unexpected = [
        e
        for e in errors
        if not any(reason in e for reason in category.expected_reasons)
    ]
    repeats = len(records) - len(parts) - len(errors)

    print(
        f"\n  загрузчик: загружено {len(parts)}, отказов {len(errors)}, повторов {repeats}"
    )
    print(f"  неожиданных отказов: {len(unexpected)}")
    for e in unexpected[:10]:
        print(f"    {e}")


def main() -> None:
    dataset = Path(
        os.environ.get("DOCYX_PATH", "~/projects/pc-part-dataset")
    ).expanduser()
    requested = sys.argv[1:] or list(CATEGORIES)

    unknown = [name for name in requested if name not in CATEGORIES]
    if unknown:
        sys.exit(f"Неизвестные категории: {unknown}. Есть: {list(CATEGORIES)}")

    for name in requested:
        category = CATEGORIES[name]
        path = dataset / "data" / "jsonl" / f"{name}.jsonl"
        if not path.exists():
            print(f"=== {name}: файл не найден — {path}\n")
            continue

        records = list(read_jsonl(path))
        print(f"=== {name}")
        explore_raw(records, category)
        if category.parse is not None:
            explore_loader(path, records, category)
        else:
            print("\n  загрузчика пока нет")
        print()


if __name__ == "__main__":
    main()
