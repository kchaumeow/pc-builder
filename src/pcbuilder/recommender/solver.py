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
from pcbuilder.domain.models import (
    Build,
    Component,
    ComponentType,
    MemoryType,
    PowerSupply,
    PsuEfficiency,
    RamKit,
    Storage,
    StorageInterface,
    StorageMedia,
)

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


# Порядок объявления в PsuEfficiency — от худшего к лучшему
EFFICIENCY_RANK = {efficiency: rank for rank, efficiency in enumerate(PsuEfficiency)}


@dataclass
class Requirements:
    """Пожелания сверх совместимости: чего сборка должна быть не хуже.

    Совместимость отвечает на «соберётся ли», требования — на «устроит ли это человека».
    Без них солвер находит буквально самое дешёвое: блок питания за $26 и одну планку памяти.
    Любое требование можно выключить: None или False.
    """

    # Память
    min_ram_gb: int = 16
    min_ram_modules: int = 2  # две планки — двухканальный режим, заметно быстрее одной
    min_ram_speed_mhz: dict[MemoryType, int] | None = (
        None  # по умолчанию — см. __post_init__
    )

    # Накопитель
    min_storage_gb: int = 500
    ssd_only: bool = True
    nvme_only: bool = True

    # Блок питания
    min_psu_efficiency: PsuEfficiency | None = PsuEfficiency.BRONZE

    def __post_init__(self) -> None:
        if self.min_ram_speed_mhz is None:
            # Ниже этого — заметная потеря производительности для своей платформы
            self.min_ram_speed_mhz = {MemoryType.DDR4: 3200, MemoryType.DDR5: 5600}

    def describe(self) -> str:
        """Требования человеческим языком — для вывода пользователю."""
        lines = [f"память ≥ {self.min_ram_gb} ГБ, планок ≥ {self.min_ram_modules}"]
        for memory_type, speed in (self.min_ram_speed_mhz or {}).items():
            lines.append(f"{memory_type.upper()} ≥ {speed} МГц")
        drive = "NVMe SSD" if self.nvme_only else "SSD" if self.ssd_only else "диск"
        lines.append(f"{drive} ≥ {self.min_storage_gb} ГБ")
        if self.min_psu_efficiency is not None:
            lines.append(f"БП не хуже {self.min_psu_efficiency}")
        return "; ".join(lines)

    def accepts(self, part: Component) -> bool:
        if isinstance(part, RamKit):
            return self._accepts_ram(part)
        if isinstance(part, Storage):
            return self._accepts_storage(part)
        if isinstance(part, PowerSupply):
            return self._accepts_psu(part)
        return True

    def _accepts_ram(self, ram: RamKit) -> bool:
        if ram.capacity_gb < self.min_ram_gb or ram.modules < self.min_ram_modules:
            return False
        min_speed = (self.min_ram_speed_mhz or {}).get(ram.memory_type)
        return min_speed is None or ram.speed_mhz >= min_speed

    def _accepts_storage(self, drive: Storage) -> bool:
        if drive.capacity_gb < self.min_storage_gb:
            return False
        if self.ssd_only and drive.media != StorageMedia.SSD:
            return False
        return not (self.nvme_only and drive.interface != StorageInterface.NVME)

    def _accepts_psu(self, psu: PowerSupply) -> bool:
        if self.min_psu_efficiency is None:
            return True
        if psu.efficiency is None:
            return False  # сертификат неизвестен — не можем подтвердить качество
        return (
            EFFICIENCY_RANK[psu.efficiency] >= EFFICIENCY_RANK[self.min_psu_efficiency]
        )


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
    if (
        category == ComponentType.COOLING
        and build.cpu is not None
        and build.cpu.includes_cooler
    ):
        return False  # кулер в коробке с процессором
    return not is_filled(build, category)


class Solver:
    def __init__(
        self,
        catalog: Catalog,
        requirements: Requirements | None = None,
        max_steps: int = 200_000,
    ):
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
        singles = (
            build.cpu,
            build.motherboard,
            build.ram,
            build.gpu,
            build.psu,
            build.case,
            build.cooling,
        )
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
        return any(
            self._fits(build, part) is not None
            for part in self.catalog.candidates(category)
        )
