from collections import Counter
from pathlib import Path

from pcbuilder.sources.docyx import read_jsonl

PATH = Path("~/projects/pc-part-dataset/data/jsonl/power-supply.jsonl").expanduser()
records = list(read_jsonl(PATH))

print(f"Всего БП: {len(records)}\n")
print("type:", Counter(r.get("type") for r in records).most_common(), "\n")
print("efficiency:", Counter(r.get("efficiency") for r in records).most_common(), "\n")
print("modular:", Counter(r.get("modular") for r in records).most_common(), "\n")

for word in ("PCIE5", "ATX 3"):
    print(f"С '{word}' в названии:", sum(1 for r in records if word in r["name"].upper()))