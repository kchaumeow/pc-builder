"""Загрузчик справочников, заполненных вручную (data/seeds/*.json).

Отличие от docyx: это наши собственные данные. Ошибка в них — опечатка, которую надо
исправить, а не «плохая запись», которую можно пропустить. Поэтому здесь ничего
не ловим: любая проблема роняет загрузку с понятным сообщением.
"""

from pathlib import Path

from pydantic import BaseModel

from pcbuilder.domain.models import Case, Component, Cooling
from pcbuilder.sources.docyx import slugify

SEEDS_DIR = Path(__file__).resolve().parents[3] / "data" / "seeds"

# Поля, которые есть в файле, но не в модели: служебные пометки
SEED_ONLY_FIELDS = {"verified"}


class SeedFile(BaseModel):
    note: str = ""
    items: list[dict]


def load_seed[T: Component](path: Path, model: type[T], prefix: str) -> dict[str, T]:
    seed = SeedFile.model_validate_json(path.read_text(encoding="utf-8"))
    parts: dict[str, T] = {}

    for index, item in enumerate(seed.items):
        data = {k: v for k, v in item.items() if k not in SEED_ONLY_FIELDS}
        data["id"] = f"{prefix}-{slugify(data['brand'] + ' ' + data['model'])}"
        try:
            part = model.model_validate(data)
        except ValueError as e:
            raise ValueError(
                f"{path.name}, запись #{index} ({item.get('brand')} {item.get('model')}): {e}"
            ) from e

        if part.id in parts:
            raise ValueError(f"{path.name}: повтор {part.id}")
        parts[part.id] = part

    return parts


def load_cases(path: Path = SEEDS_DIR / "cases.json") -> dict[str, Case]:
    return load_seed(path, Case, "case")


def load_coolers(path: Path = SEEDS_DIR / "coolers.json") -> dict[str, Cooling]:
    return load_seed(path, Cooling, "cooler")


def unverified(path: Path) -> list[str]:
    """Какие записи ещё не сверены с сайтом производителя."""
    seed = SeedFile.model_validate_json(path.read_text(encoding="utf-8"))
    return [f"{i['brand']} {i['model']}" for i in seed.items if not i.get("verified")]
