"""Budget picking: the best build for the workload that fits within the amount.

Idea: iterate over CPU + GPU pairs from the best score to the worst. For each pair
the solver fills in the rest as cheaply as it can. The first pair whose full build
fits the budget is the answer: every better pair has already failed to fit.

To avoid running the solver for pairs that are clearly too expensive, compute a lower
bound first: CPU + GPU + the cheapest suitable part in each remaining category.
If even that exceeds the budget, the pair is skipped without a search.
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
    pairs_considered: int  # how many CPU+GPU pairs were considered
    pairs_solved: int  # how many of them the solver ran for


def cheapest_per_key[T](parts: list[T], key) -> list[T]:
    """The first part from each group (by key). The list is already sorted by price,
    so the first is the cheapest: out of ten RTX 4070s we need just one."""
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

    # Lower bound on the cost of the rest: the cheapest suitable part in each category
    rest_floor = Decimal(0)
    for category in FILL_ORDER:
        if category == ComponentType.CPU:
            continue
        accepted = [p for p in catalog.candidates(category) if requirements.accepts(p)]
        if not accepted:
            return None  # some category has nothing to buy at all
        rest_floor += catalog.price(accepted[0])

    pairs = [(profile.score(cpu, gpu), cpu, gpu) for cpu in cpus for gpu in gpus]
    # Best first; on equal scores, cheapest first
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
