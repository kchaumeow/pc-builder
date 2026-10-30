from collections import Counter
from pathlib import Path

from pcbuilder.sources.docyx import load_parts, parse_motherboard

PATH = Path("~/Projects/pc-part-dataset/data/jsonl/motherboard.jsonl").expanduser()

parts, errors = load_parts(PATH, parse_motherboard)
print(f"\nЗагружено: {len(parts)}, ошибок: {len(errors)}")

expected = ("Unsupported socket", "Unknown form factor", "Unknown chipset", "Cannot determine memory type")
unexpected = [e for e in errors if not any(reason in e for reason in expected)]
print(f"Неожиданных ошибок: {len(unexpected)}")
for e in unexpected[:20]:
    print(" ", e)

print()
print("По сокетам:", Counter(p.socket for p in parts.values()))
print("Сокет + память:", Counter((p.socket, p.memory_type) for p in parts.values()))