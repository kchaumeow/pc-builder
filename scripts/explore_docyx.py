"""Explore the docyx dataset and check the loaders.

Two steps per category:
  1. Raw records: how many in total, how many lack important fields, which values occur.
     Always works — even for categories that don't have a loader yet.
  2. Loader (if already written): how many loaded, how many rejected,
     and whether any rejections are unexpected — i.e. not on the list of known reasons.

Run from the project root:
    python scripts/explore_docyx.py                    # all categories
    python scripts/explore_docyx.py video-card         # one category
    python scripts/explore_docyx.py cpu memory         # several

Dataset path: the DOCYX_PATH environment variable or ~/projects/pc-part-dataset.
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
    parse: Callable | None = None  # None — no loader yet
    expected_reasons: tuple[str, ...] = ()  # known, accepted rejection reasons
    count_fields: tuple[str, ...] = ()  # fields whose values to count
    required_fields: tuple[str, ...] = ()  # fields whose absence is worth seeing
    top: int = 15  # how many of the most common values to show


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
    print(f"  records: {len(records)}")
    for name in category.required_fields:
        missing = sum(1 for r in records if r.get(name) is None)
        print(f"  missing '{name}': {missing}")

    for name in category.count_fields:
        counts = Counter(r.get(name) for r in records)
        print(f"\n  '{name}' — {len(counts)} distinct values, most common:")
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
        f"\n  loader: loaded {len(parts)}, rejected {len(errors)}, duplicates {repeats}"
    )
    print(f"  unexpected rejections: {len(unexpected)}")
    for e in unexpected[:10]:
        print(f"    {e}")


def main() -> None:
    dataset = Path(
        os.environ.get("DOCYX_PATH", "~/projects/pc-part-dataset")
    ).expanduser()
    requested = sys.argv[1:] or list(CATEGORIES)

    unknown = [name for name in requested if name not in CATEGORIES]
    if unknown:
        sys.exit(f"Unknown categories: {unknown}. Available: {list(CATEGORIES)}")

    for name in requested:
        category = CATEGORIES[name]
        path = dataset / "data" / "jsonl" / f"{name}.jsonl"
        if not path.exists():
            print(f"=== {name}: file not found — {path}\n")
            continue

        records = list(read_jsonl(path))
        print(f"=== {name}")
        explore_raw(records, category)
        if category.parse is not None:
            explore_loader(path, records, category)
        else:
            print("\n  no loader yet")
        print()


if __name__ == "__main__":
    main()
