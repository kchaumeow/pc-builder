"""Прогон всех загрузчиков по настоящему датасету: сколько загрузилось, сколько отказов и почему.

Запуск из корня проекта:
    python scripts/explore_docyx.py ~/projects/pc-part-dataset
"""

import sys
from collections import Counter
from pathlib import Path

from pcbuilder.sources.docyx import (
    load_parts,
    parse_cpu,
    parse_memory,
    parse_motherboard,
    parse_power_supply,
    read_jsonl,
)

# Файл → (функция разбора, ожидаемые причины отказа)
LOADERS = {
    "memory.jsonl": (parse_memory, ("Unknown DDR version", "Unexpected speed format")),
    "cpu.jsonl": (parse_cpu, ("Unknown microarchitecture", "not supported")),
    "motherboard.jsonl": (
        parse_motherboard,
        ("Unsupported socket", "Unknown form factor", "Unknown chipset", "Cannot determine memory type"),
    ),
    "power-supply.jsonl": (parse_power_supply, ("Unsupported PSU form factor",)),
}

dataset = Path(sys.argv[1] if len(sys.argv) > 1 else "~/projects/pc-part-dataset").expanduser()

for filename, (parse, expected) in LOADERS.items():
    path = dataset / "data" / "jsonl" / filename
    total = sum(1 for _ in read_jsonl(path))
    parts, errors = load_parts(path, parse)
    unexpected = [e for e in errors if not any(reason in e for reason in expected)]

    print(f"=== {filename}")
    print(f"  записей {total}, загружено {len(parts)}, отказов {len(errors)}, "
          f"повторов {total - len(parts) - len(errors)}")
    print(f"  неожиданных отказов: {len(unexpected)}")
    for e in unexpected[:10]:
        print("   ", e)
    print()

    if filename == "motherboard.jsonl":
        print("  сокет + память:", Counter((p.socket, str(p.memory_type)) for p in parts.values()))
        print()
    if filename == "power-supply.jsonl":
        print("  форм-факторы:", Counter(str(p.form_factor) for p in parts.values()))
        print("  12VHPWR:", Counter(p.has_12vhpwr for p in parts.values()))
        print()