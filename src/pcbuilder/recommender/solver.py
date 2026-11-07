"""Солвер v1: достроить сборку самыми дешёвыми совместимыми деталями.

Поиск с возвратом (backtracking): категории заполняются по очереди, кандидаты
перебираются от дешёвых к дорогим, после каждой детали — check() частичной сборки.
Если в какой-то категории ничего не подошло — возвращаемся и меняем предыдущий выбор.

Ограничение v1: «дешёвое в каждой категории по очереди» даёт очень дешёвую сборку,
но не гарантирует самую дешёвую из возможных.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from pcbuilder.catalog import Catalog
from pcbuilder.domain.compatibility import Issue, Severity, check
from pcbuilder.domain.models import Build, Component, ComponentType, RamKit, Storage, StorageMedia

# Порядок важен для скорости: сначала то, что сильнее всего ограничивает остальное.
# Плата сразу после процессора (сокет), память после платы (тип), корпус после платы,
# видеокарты и БП (форм-факторы и длины), кулер последним (сокет и высота под корпус).
# Видеокарту солвер не выбирает: её задаёт пользователь (или её нет — встроенная графика).
FILL_ORDER: tuple[ComponentType, ...] = (
    ComponentType.CPU,
    ComponentType.MOTHERBOARD,
    ComponentType.RAM,
    ComponentType.STORAGE,
    ComponentType.POWER_SUPPLY,
    ComponentType.CASE,
    ComponentType.COOLING,
)

BUILD_FIELDS = {
    ComponentType.CPU: "cpu",
    ComponentType.MOTHERBOARD: "motherboard",
    ComponentType.RAM: "ram",
    ComponentType.GPU: "gpu",
    ComponentType.POWER_SUPPLY: "psu",
    ComponentType.CASE: "case",
    ComponentType.COOLING: "cooling",
}


@dataclass
class Requirements:
    """Пожелания сверх совместимости. Без них солвер найдёт 8 ГБ памяти и диск на 128 ГБ."""

    min_ram_gb: int = 16
    min_storage_gb: int = 500
    ssd_only: bool = True

    def accepts(self, part: Component) -> bool:
        if isinstance(part, RamKit):
            return part.capacity_gb >= self.min_ram_gb
        if isinstance(part, Storage):
            if self.ssd_only and part.media != StorageMedia.SSD:
                return False
            return part.capacity_gb >= self.min_storage_gb
        return True


@dataclass
class Solution:
    build: Build
    total: Decimal
    issues: list[Issue]  # только предупреждения: сборки с ошибками солвер не возвращает
    steps: int  # сколько раз проверялась деталь — для понимания цены поиска


class SearchLimitReached(Exception):
    pass


def has_errors(issues: list[Issue]) -> bool:
    return any(issue.severity == Severity.ERROR for issue in issues)


def with_part(build: Build, part: Component) -> Build:
    """Новая сборка с добавленной деталью. Исходная не меняется — это важно для возврата."""
    if part.category == ComponentType.STORAGE:
        return build.model_copy(update={"storage": [*build.storage, part]})
    return build.model_copy(update={BUILD_FIELDS[part.category]: part})


def is_filled(build: Build, category: ComponentType) -> bool:
    if category == ComponentType.STORAGE:
        return bool(build.storage)
    return getattr(build, BUILD_FIELDS[category]) is not None


def needs(build: Build, category: ComponentType) -> bool:
    """Нужна ли сборке деталь этой категории."""
    if category == ComponentType.COOLING and build.cpu is not None and build.cpu.includes_cooler:
        return False  # кулер в коробке с процессором
    return not is_filled(build, category)


class Solver:
    def __init__(self, catalog: Catalog, requirements: Requirements | None = None, max_steps: int = 200_000):
        self.catalog = catalog
        self.requirements = requirements or Requirements()
        self.max_steps = max_steps
        self.steps = 0

    def complete(self, build: Build) -> Solution | None:
        """Достроить сборку. None — совместимого варианта нет."""
        self.steps = 0
        if has_errors(check(build)):
            return None  # уже выбранные детали несовместимы между собой
        result = self._search(build, [c for c in FILL_ORDER if needs(build, c)])
        if result is None:
            return None
        return Solution(
            build=result,
            total=self.total(result),
            issues=check(result, complete=True),
            steps=self.steps,
        )

    def total(self, build: Build) -> Decimal:
        singles = (build.cpu, build.motherboard, build.ram, build.gpu, build.psu, build.case, build.cooling)
        parts: list[Component] = [p for p in singles if p is not None]
        parts.extend(build.storage)
        return sum((self.catalog.price(p) for p in parts), Decimal(0))

    def _fits(self, build: Build, part: Component) -> Build | None:
        """Сборка с деталью, если деталь подходит; иначе None."""
        self.steps += 1
        if self.steps > self.max_steps:
            raise SearchLimitReached(f"Search stopped after {self.max_steps} checks")
        if not self.requirements.accepts(part):
            return None
        candidate = with_part(build, part)
        return None if has_errors(check(candidate)) else candidate

    def _search(self, build: Build, remaining: Sequence[ComponentType]) -> Build | None:
        if not remaining:
            return None if has_errors(check(build, complete=True)) else build

        category, rest = remaining[0], remaining[1:]
        for part in self.catalog.candidates(category):
            candidate = self._fits(build, part)
            if candidate is None:
                continue
            # Заглядывание вперёд: если для какой-то из следующих категорий уже не осталось
            # ни одной подходящей детали, этот выбор — тупик, и спускаться в него незачем.
            if not all(self._any_fits(candidate, later) for later in rest):
                continue
            result = self._search(candidate, rest)
            if result is not None:
                return result
        return None

    def _any_fits(self, build: Build, category: ComponentType) -> bool:
        return any(self._fits(build, part) is not None for part in self.catalog.candidates(category))