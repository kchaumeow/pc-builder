"""Как показывать детали человеку: подписи категорий и короткие характеристики."""

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

# Порядок — как человек обычно читает список деталей сборки
CATEGORY_LABELS: dict[ComponentType, tuple[str, str]] = {
    ComponentType.CPU: ("cpu", "Процессор"),
    ComponentType.GPU: ("gpu", "Видеокарта"),
    ComponentType.MOTHERBOARD: ("motherboard", "Материнская плата"),
    ComponentType.RAM: ("ram", "Память"),
    ComponentType.STORAGE: ("storage", "Накопитель"),
    ComponentType.POWER_SUPPLY: ("psu", "Блок питания"),
    ComponentType.CASE: ("case", "Корпус"),
    ComponentType.COOLING: ("cooling", "Кулер"),
}


def describe(part: Component) -> str:
    """Главные характеристики детали одной строкой."""
    match part:
        case CPU():
            return f"{part.socket}, {part.cores} ядер"
        case GPU():
            return f"{part.chipset}, {part.vram_gb} ГБ, {part.length_mm} мм"
        case Motherboard():
            return f"{part.chipset}, {part.form_factor}, {part.memory_type.upper()}"
        case RamKit():
            per_module = part.capacity_gb // part.modules
            return f"{part.modules}×{per_module} ГБ {part.memory_type.upper()}-{part.speed_mhz}"
        case Storage():
            return f"{part.capacity_gb} ГБ, {part.kind}"
        case PowerSupply():
            return f"{part.wattage_w} Вт, {part.efficiency or 'без сертификата'}"
        case Case():
            return f"видеокарта до {part.max_gpu_length_mm} мм, кулер до {part.max_cooler_height_mm} мм"
        case Cooling():
            return (
                f"башня {part.height_mm} мм"
                if part.height_mm
                else f"водянка {part.radiator_mm} мм"
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


def part_views(build: Build, catalog: Catalog) -> list[PartView]:
    views = []
    for part in build_parts(build):
        key, label = CATEGORY_LABELS[part.category]
        views.append(
            PartView(
                category=key,
                label=label,
                id=part.id,
                name=part.name,
                details=describe(part),
                price=catalog.price(part),
            )
        )
    return views
