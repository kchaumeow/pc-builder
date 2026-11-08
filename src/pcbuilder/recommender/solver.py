"""Solver v1: complete a build with the cheapest compatible parts.

Backtracking search: categories are filled one at a time, candidates are tried from
cheapest to most expensive, and the partial build is check()ed after each part.
If nothing fits in some category, we backtrack and change an earlier choice.

v1 limitation: "cheapest in each category in turn" yields a very cheap build,
but doesn't guarantee the cheapest possible one.
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

# Order matters for speed: whatever constrains the rest the most goes first.
# Motherboard right after the CPU (socket), memory after the motherboard (type), case
# after the motherboard, GPU and PSU (form factors and lengths), cooler last (socket and
# case height). The solver doesn't pick the GPU: the user sets it (or there is none —
# integrated graphics).
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


# PsuEfficiency members are declared from worst to best
EFFICIENCY_RANK = {efficiency: rank for rank, efficiency in enumerate(PsuEfficiency)}


@dataclass
class Requirements:
    """Requirements beyond compatibility: the minimum the build must meet.

    Compatibility answers "will it go together", requirements answer "will it satisfy
    the person". Without them the solver finds the literal cheapest: a $26 PSU and a
    single memory stick. Any requirement can be turned off with None or False.
    """

    # Memory
    min_ram_gb: int = 16
    min_ram_modules: int = 2  # two sticks — dual channel, noticeably faster than one
    min_ram_speed_mhz: dict[MemoryType, int] | None = None  # default: see __post_init__

    # Storage
    min_storage_gb: int = 500
    ssd_only: bool = True
    nvme_only: bool = True

    # Power supply
    min_psu_efficiency: PsuEfficiency | None = PsuEfficiency.BRONZE

    def __post_init__(self) -> None:
        if self.min_ram_speed_mhz is None:
            # Below this, the platform loses noticeable performance
            self.min_ram_speed_mhz = {MemoryType.DDR4: 3200, MemoryType.DDR5: 5600}

    def describe(self) -> str:
        """Requirements in plain language, for showing to the user."""
        lines = [f"RAM ≥ {self.min_ram_gb} GB, ≥ {self.min_ram_modules} modules"]
        for memory_type, speed in (self.min_ram_speed_mhz or {}).items():
            lines.append(f"{memory_type.upper()} ≥ {speed} MHz")
        drive = "NVMe SSD" if self.nvme_only else "SSD" if self.ssd_only else "drive"
        lines.append(f"{drive} ≥ {self.min_storage_gb} GB")
        if self.min_psu_efficiency is not None:
            lines.append(f"PSU {self.min_psu_efficiency} or better")
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
            return False  # certification unknown — can't confirm quality
        return (
            EFFICIENCY_RANK[psu.efficiency] >= EFFICIENCY_RANK[self.min_psu_efficiency]
        )


@dataclass
class Solution:
    build: Build
    total: Decimal
    issues: list[Issue]  # warnings only: the solver never returns builds with errors
    steps: int  # how many times a part was checked — shows the cost of the search


class SearchLimitReached(Exception):
    pass


def has_errors(issues: list[Issue]) -> bool:
    return any(issue.severity == Severity.ERROR for issue in issues)


def with_part(build: Build, part: Component) -> Build:
    """A new build with the part added. The original is unchanged — backtracking relies on that."""
    if part.category == ComponentType.STORAGE:
        return build.model_copy(update={"storage": [*build.storage, part]})
    return build.model_copy(update={BUILD_FIELDS[part.category]: part})


def is_filled(build: Build, category: ComponentType) -> bool:
    if category == ComponentType.STORAGE:
        return bool(build.storage)
    return getattr(build, BUILD_FIELDS[category]) is not None


def needs(build: Build, category: ComponentType) -> bool:
    """Whether the build needs a part of this category."""
    if (
        category == ComponentType.COOLING
        and build.cpu is not None
        and build.cpu.includes_cooler
    ):
        return False  # the cooler comes boxed with the CPU
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
        """Complete the build. None means no compatible option exists."""
        self.steps = 0
        if has_errors(check(build)):
            return None  # the parts already chosen are incompatible with each other
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
        """The build with the part if it fits; otherwise None."""
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
            # Look-ahead: if some later category has no suitable part left, this choice
            # is a dead end and there's no point descending into it.
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
