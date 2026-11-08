"""How to present parts to people: category labels and short specs."""

from pcbuilder.api.schemas import PartView
from pcbuilder.catalog import Catalog
from pcbuilder.domain.models import (
    CPU,
    GPU,
    Build,
    Case,
    Component,
    ComponentType,
    Cooling,
    Motherboard,
    PowerSupply,
    RamKit,
    Storage,
)

# Order matches how people usually read a build's parts list
CATEGORY_LABELS: dict[ComponentType, tuple[str, str]] = {
    ComponentType.CPU: ("cpu", "CPU"),
    ComponentType.GPU: ("gpu", "Graphics card"),
    ComponentType.MOTHERBOARD: ("motherboard", "Motherboard"),
    ComponentType.RAM: ("ram", "Memory"),
    ComponentType.STORAGE: ("storage", "Storage"),
    ComponentType.POWER_SUPPLY: ("psu", "Power supply"),
    ComponentType.CASE: ("case", "Case"),
    ComponentType.COOLING: ("cooling", "CPU cooler"),
}


def describe(part: Component) -> str:
    """A part's key specs in one line."""
    match part:
        case CPU():
            return f"{part.socket}, {part.cores} cores"
        case GPU():
            return f"{part.chipset}, {part.vram_gb} GB, {part.length_mm} mm"
        case Motherboard():
            return f"{part.chipset}, {part.form_factor}, {part.memory_type.upper()}"
        case RamKit():
            per_module = part.capacity_gb // part.modules
            return f"{part.modules}×{per_module} GB {part.memory_type.upper()}-{part.speed_mhz}"
        case Storage():
            return f"{part.capacity_gb} GB, {part.kind}"
        case PowerSupply():
            return f"{part.wattage_w} W, {part.efficiency or 'no certification'}"
        case Case():
            return f"GPU up to {part.max_gpu_length_mm} mm, cooler up to {part.max_cooler_height_mm} mm"
        case Cooling():
            return (
                f"tower {part.height_mm} mm"
                if part.height_mm
                else f"AIO {part.radiator_mm} mm"
            )
    return ""


def build_parts(build: Build) -> list[Component]:
    singles = [build.cpu, build.gpu, build.motherboard, build.ram]
    rest = [build.psu, build.case, build.cooling]
    return (
        [p for p in singles if p is not None]
        + list(build.storage)
        + [p for p in rest if p is not None]
    )


def part_view(part: Component, catalog: Catalog) -> PartView:
    key, label = CATEGORY_LABELS[part.category]
    return PartView(
        category=key,
        label=label,
        id=part.id,
        name=part.name,
        details=describe(part),
        price=catalog.price(part),
    )


def part_views(build: Build, catalog: Catalog) -> list[PartView]:
    return [part_view(part, catalog) for part in build_parts(build)]
