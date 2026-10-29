from collections import Counter
from pathlib import Path

from pcbuilder.sources.docyx import load_parts, parse_memory, read_jsonl

PATH = Path("~/Projects/pc-part-dataset/data/jsonl/memory.jsonl").expanduser()

total = sum(1 for _ in read_jsonl(PATH))
parts, errors = load_parts(PATH, parse_memory)

print(f"Записей в файле: {total}")
print(f"Загружено:       {len(parts)}")
print(f"Ошибок:          {len(errors)}")
print(f"Дубликатов:      {total - len(parts) - len(errors)}")
print()
print("По типу памяти:", Counter(p.memory_type for p in parts.values()))
print()
print("Первые ошибки:")
for e in errors[:10]:
    print(" ", e)