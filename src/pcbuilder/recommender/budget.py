"""Подбор под бюджет: лучшая сборка для задачи, которая укладывается в сумму.

Идея: перебираем пары «процессор + видеокарта» от лучшей по оценке к худшей.
Для каждой пары солвер достраивает остальное подешевле. Первая пара, у которой
полная сборка уложилась в бюджет, — ответ: все пары лучше неё уже не уложились.

Чтобы не запускать солвер для заведомо дорогих пар, сначала считаем нижнюю границу:
процессор + видеокарта + самые дешёвые подходящие детали остальных категорий.
Если даже она больше бюджета — пару пропускаем без поиска.
"""

from dataclasses import dataclass
from decimal import Decimal

from pcbuilder.catalog import Catalog
from pcbuilder.domain.models import CPU, GPU, Build, ComponentType
from pcbuilder.recommender.scores import GAMING, Profile
from pcbuilder.recommender.solver import FILL_ORDER, Requirements, Solution, Solver


@dataclass
class BudgetResult:
    solution: Solution
    score: float
    pairs_considered: int  # сколько пар процессор+видеокарта рассмотрено
    pairs_solved: int  # для скольких из них запускался солвер


def cheapest_per_key[T](parts: list[T], key) -> list[T]:
    """Из каждой группы (по key) — первая деталь. Список уже отсортирован по цене,
    так что первая — самая дешёвая: из десяти RTX 4070 нужна одна."""
    seen: dict[object, T] = {}
    for part in parts:
        seen.setdefault(key(part), part)
    return list(seen.values())


def best_build(
    catalog: Catalog,
    budget: Decimal,
    profile: Profile = GAMING,
    requirements: Requirements | None = None,
    max_solved_pairs: int = 300,
) -> BudgetResult | None:
    requirements = requirements or Requirements()
    solver = Solver(catalog, requirements)

    cpus = [c for c in catalog.candidates(ComponentType.CPU) if isinstance(c, CPU)]
    gpus = cheapest_per_key(
        [g for g in catalog.candidates(ComponentType.GPU) if isinstance(g, GPU)],
        key=lambda g: g.chipset,
    )

    # Нижняя граница стоимости остального: самая дешёвая подходящая деталь каждой категории
    rest_floor = Decimal(0)
    for category in FILL_ORDER:
        if category == ComponentType.CPU:
            continue
        accepted = [p for p in catalog.candidates(category) if requirements.accepts(p)]
        if not accepted:
            return None  # в какой-то категории нечего купить вообще
        rest_floor += catalog.price(accepted[0])

    pairs = [(profile.score(cpu, gpu), cpu, gpu) for cpu in cpus for gpu in gpus]
    # Лучшие — первыми; при равной оценке — дешёвые
    pairs.sort(key=lambda p: (-p[0], catalog.price(p[1]) + catalog.price(p[2])))

    solved = 0
    for considered, (score, cpu, gpu) in enumerate(pairs, start=1):
        if catalog.price(cpu) + catalog.price(gpu) + rest_floor > budget:
            continue
        solved += 1
        if solved > max_solved_pairs:
            return None
        solution = solver.complete(Build(cpu=cpu, gpu=gpu))
        if solution is not None and solution.total <= budget:
            return BudgetResult(solution, score, considered, solved)
    return None
