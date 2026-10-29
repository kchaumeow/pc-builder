from collections import Counter
from pathlib import Path

from pcbuilder.sources.docyx import load_parts, parse_cpu, read_jsonl

PATH = Path("~/Projects/pc-part-dataset/data/jsonl/cpu.jsonl").expanduser()

total = sum(1 for _ in read_jsonl(PATH))
parts, errors = load_parts(PATH, parse_cpu)
for p in parts.values():
    if "Threadripper" in p.name:
        print(p.name, p.socket)
records = list(read_jsonl(PATH))

print(f"Записей в файле: {total}")
print(f"Загружено:       {len(parts)}")
print(f"Ошибок:          {len(errors)}")
print(f"Дубликатов:      {total - len(parts) - len(errors)}")
print()
# print("По типу архитектуры:", Counter(r["microarchitecture"] for r in records))
print()
print("Первые ошибки:")
for e in errors[:10]:
    print(" ", e)