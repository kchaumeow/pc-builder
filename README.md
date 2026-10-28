# pcbuilder

Подбор комплектующих ПК из нескольких источников с проверкой совместимости.

## Запуск
```
pip install -e ".[dev]"
pre-commit install
pytest
```

## Git hooks
`pre-commit install` ставит два хука (pytest запускается из `.venv` проекта, активировать окружение не нужно):
- **pre-commit**: `ruff check --fix`, `ruff format`, `pytest`
- **commit-msg**: формат gitmoji `<emoji> (<scope>): <subject>`, например `🐛 (api): return 404 for unknown build`

Проверить всё вручную: `pre-commit run --all-files`.

## Статус
- [x] Шаг 1: доменные модели + правила совместимости (`src/pcbuilder/domain`)
- [ ] Шаг 2: БД и загрузка открытого датасета
- [ ] Шаг 3: коннектор цен Geizhals + матчинг товаров
- [ ] Шаг 4: солвер подбора под бюджет
- [ ] Шаг 5: API + UI
- [ ] Шаг 6: планировщик обновлений, остальные источники