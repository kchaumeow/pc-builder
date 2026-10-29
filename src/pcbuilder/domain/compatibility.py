import math
from collections.abc import Callable
from enum import StrEnum

from pydantic import BaseModel

from pcbuilder.domain.models import Build, StorageFormFactor

BASE_SYSTEM_POWER_W: int = 75  # плата, память, диски, вентиляторы
PSU_HEADROOM: float = 1.25  # запас: пики потребления, старение БП
ADAPTER_MIN_8PIN: int = 2  # переходник 12VHPWR берёт минимум два 8-pin


class Severity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class Issue(BaseModel):
    severity: Severity
    rule: str  # короткий код правила
    message: str  # текст для человека


def _error(rule: str, message: str) -> Issue:
    return Issue(severity=Severity.ERROR, rule=rule, message=message)


def _warning(rule: str, message: str) -> Issue:
    return Issue(severity=Severity.WARNING, rule=rule, message=message)


def estimated_power_w(build: Build) -> int:
    """Оценка потребления сборки, без запаса."""
    total = BASE_SYSTEM_POWER_W
    if build.cpu:
        total += build.cpu.tdp_w
    if build.gpu:
        total += build.gpu.tdp_w
    return total


# --- Правила совместимости ---------------------------------------------------------
# Проверяют противоречия между уже выбранными деталями.
# Если нужной детали нет — молчат: сборка подбирается по шагам.


def cpu_socket_matches_motherboard(build: Build) -> list[Issue]:
    if not (build.cpu and build.motherboard):
        return []
    if build.cpu.socket != build.motherboard.socket:
        return [
            _error(
                "CPU_SOCKET_MISMATCH",
                f"CPU socket {build.cpu.socket} does not match motherboard socket {build.motherboard.socket}",
            )
        ]
    return []


def ram_matches_motherboard(build: Build) -> list[Issue]:
    issues: list[Issue] = []
    if not (build.ram and build.motherboard):
        return issues

    ram, mb = build.ram, build.motherboard

    if ram.memory_type != mb.memory_type:
        issues.append(
            _error(
                "RAM_MEMORY_TYPE_MISMATCH",
                f"RAM memory type {ram.memory_type} does not match motherboard memory type {mb.memory_type}",
            )
        )
    if ram.modules > mb.memory_slots:
        issues.append(
            _error(
                "RAM_MODULES_EXCEEDS_SLOTS",
                f"Number of RAM modules {ram.modules} exceeds motherboard memory slots {mb.memory_slots}",
            )
        )
    if ram.capacity_gb > mb.max_memory_gb:
        issues.append(
            _error(
                "RAM_CAPACITY_EXCEEDS_MOTHERBOARD_LIMIT",
                f"RAM capacity {ram.capacity_gb}GB exceeds motherboard max memory {mb.max_memory_gb}GB",
            )
        )
    return issues


def ram_matches_cpu(build: Build) -> list[Issue]:
    if not (build.ram and build.cpu):
        return []

    ram, cpu = build.ram, build.cpu

    if ram.memory_type not in cpu.memory_types:
        return [
            _error(
                "RAM_MEMORY_TYPE_NOT_SUPPORTED_BY_CPU",
                f"RAM memory type {ram.memory_type} is not supported by CPU (supports: {', '.join(cpu.memory_types)})",
            )
        ]
    return []


def psu_wattage_sufficient(build: Build) -> list[Issue]:
    issues: list[Issue] = []
    if not build.psu:
        return issues

    gpu, psu = build.gpu, build.psu
    required_power = math.ceil(estimated_power_w(build) * PSU_HEADROOM)

    if psu.wattage_w < required_power:
        issues.append(
            _error(
                "PSU_WATTAGE_INSUFFICIENT",
                f"PSU wattage {psu.wattage_w}W is less than the estimated required power {required_power}W (including headroom)",
            )
        )
    if gpu and gpu.recommended_psu_w is not None and psu.wattage_w < gpu.recommended_psu_w:
        issues.append(
            _warning(
                "PSU_BELOW_GPU_RECOMMENDATION",
                f"PSU {psu.wattage_w}W is below GPU manufacturer recommendation {gpu.recommended_psu_w}W",
            )
        )
    return issues


def psu_has_gpu_connectors(build: Build) -> list[Issue]:
    issues: list[Issue] = []
    if not (build.psu and build.gpu):
        return issues

    psu, gpu = build.psu, build.gpu
    gpu_8_pin_connectors = gpu.power_connectors.count("8-pin")
    needs_12vhpwr = "12VHPWR" in gpu.power_connectors

    if gpu_8_pin_connectors > psu.pcie_8pin:
        issues.append(
            _error(
                "PSU_INSUFFICIENT_8PIN_CONNECTORS",
                f"GPU requires {gpu_8_pin_connectors} 8-pin connectors, but PSU has only {psu.pcie_8pin}",
            )
        )
    if needs_12vhpwr and not psu.has_12vhpwr:
        if psu.pcie_8pin < ADAPTER_MIN_8PIN:
            issues.append(
                _error(
                    "PSU_MISSING_12VHPWR_CONNECTOR",
                    f"GPU requires 12VHPWR; PSU has no native cable and only {psu.pcie_8pin} 8-pin for an adapter",
                )
            )
        else:
            issues.append(
                _warning(
                    "PSU_12VHPWR_VIA_ADAPTER",
                    "GPU requires 12VHPWR; PSU has no native cable — an adapter will be needed",
                )
            )
    return issues


def motherboard_fits_case(build: Build) -> list[Issue]:
    if not (build.motherboard and build.case):
        return []

    mb, case = build.motherboard, build.case

    if mb.form_factor not in case.supported_motherboard_form_factors:
        return [
            _error(
                "MOTHERBOARD_DOES_NOT_FIT_CASE",
                f"Motherboard form factor {mb.form_factor} is not supported by the case "
                f"(supports: {', '.join(case.supported_motherboard_form_factors)})",
            )
        ]
    return []


def gpu_fits_case(build: Build) -> list[Issue]:
    if not (build.gpu and build.case):
        return []

    gpu, case = build.gpu, build.case

    if gpu.length_mm > case.max_gpu_length_mm:
        return [
            _error(
                "GPU_TOO_LONG_FOR_CASE",
                f"GPU length {gpu.length_mm}mm exceeds case max GPU length {case.max_gpu_length_mm}mm",
            )
        ]
    return []


def cooler_fits_case(build: Build) -> list[Issue]:
    if not (build.cooling and build.case):
        return []

    cooler, case = build.cooling, build.case

    if cooler.height_mm is not None and cooler.height_mm > case.max_cooler_height_mm:
        return [
            _error(
                "COOLER_TOO_TALL_FOR_CASE",
                f"Cooler height {cooler.height_mm}mm exceeds case max cooler height {case.max_cooler_height_mm}mm",
            )
        ]
    return []


def psu_fits_case(build: Build) -> list[Issue]:
    issues: list[Issue] = []
    if not (build.psu and build.case):
        return issues

    psu, case = build.psu, build.case

    if psu.form_factor not in case.psu_form_factors:
        issues.append(
            _error(
                "PSU_FORM_FACTOR_NOT_SUPPORTED_BY_CASE",
                f"PSU form factor {psu.form_factor} is not supported by the case "
                f"(supports: {', '.join(case.psu_form_factors)})",
            )
        )
    if (
        psu.length_mm is not None
        and case.max_psu_length_mm is not None
        and psu.length_mm > case.max_psu_length_mm
    ):
        issues.append(
            _error(
                "PSU_TOO_LONG_FOR_CASE",
                f"PSU length {psu.length_mm}mm exceeds case max PSU length {case.max_psu_length_mm}mm",
            )
        )
    return issues


def cooler_supports_cpu(build: Build) -> list[Issue]:
    if not (build.cooling and build.cpu):
        return []

    cooler, cpu = build.cooling, build.cpu

    if cpu.socket not in cooler.sockets:
        return [
            _error(
                "COOLER_NOT_COMPATIBLE_WITH_CPU_SOCKET",
                f"Cooler does not support CPU socket {cpu.socket} (supports: {', '.join(cooler.sockets)})",
            )
        ]
    return []


def cooler_handles_tdp(build: Build) -> list[Issue]:
    if not (build.cooling and build.cpu):
        return []

    cooler, cpu = build.cooling, build.cpu

    if cooler.max_tdp_w is not None and cpu.tdp_w > cooler.max_tdp_w:
        return [
            _warning(
                "COOLER_TDP_TOO_LOW_FOR_CPU",
                f"Cooler max TDP {cooler.max_tdp_w}W is less than CPU TDP {cpu.tdp_w}W",
            )
        ]
    return []


def storage_fits_motherboard(build: Build) -> list[Issue]:
    issues: list[Issue] = []
    if not (build.storage and build.motherboard):
        return issues

    mb = build.motherboard
    # Порт определяется форм-фактором: M.2 (даже SATA-интерфейс) занимает M.2-слот,
    # 2.5" и 3.5" подключаются к SATA-портам.
    m2_count = sum(1 for s in build.storage if s.form_factor == StorageFormFactor.M2)
    sata_count = len(build.storage) - m2_count

    if m2_count > mb.m2_slots:
        issues.append(
            _error(
                "STORAGE_TOO_MANY_M2",
                f"{m2_count} M.2 drives, motherboard has {mb.m2_slots} M.2 slots",
            )
        )
    if sata_count > mb.sata_ports:
        issues.append(
            _error(
                "STORAGE_TOO_MANY_SATA",
                f"{sata_count} SATA drives, motherboard has {mb.sata_ports} SATA ports",
            )
        )
    return issues


# --- Правила полноты ---------------------------------------------------------------
# Срабатывают из-за ОТСУТСТВИЯ детали, поэтому применяются только к законченной сборке.


def cpu_has_cooling(build: Build) -> list[Issue]:
    if not build.cpu:
        return []
    if not build.cooling and not build.cpu.includes_cooler:
        return [
            _error(
                "CPU_NO_COOLING",
                f"CPU {build.cpu.name} has no boxed cooler and no cooler is selected",
            )
        ]
    return []


def has_graphics_output(build: Build) -> list[Issue]:
    if not build.cpu:
        return []
    if not build.gpu and not build.cpu.integrated_graphics:
        return [
            _error(
                "NO_GRAPHICS_OUTPUT",
                "No GPU selected and CPU has no integrated graphics",
            )
        ]
    return []


# --- Запуск ------------------------------------------------------------------------

Rule = Callable[[Build], list[Issue]]

COMPATIBILITY_RULES: list[Rule] = [
    cpu_socket_matches_motherboard,
    ram_matches_motherboard,
    ram_matches_cpu,
    psu_wattage_sufficient,
    psu_has_gpu_connectors,
    motherboard_fits_case,
    gpu_fits_case,
    cooler_fits_case,
    psu_fits_case,
    cooler_supports_cpu,
    cooler_handles_tdp,
    storage_fits_motherboard,
]

COMPLETENESS_RULES: list[Rule] = [
    cpu_has_cooling,
    has_graphics_output,
]


def check(build: Build, complete: bool = False) -> list[Issue]:
    """Проверить сборку.

    complete=False — по ходу подбора: только противоречия между выбранными деталями.
    complete=True  — законченная сборка: плюс проверки на недостающие детали.
    """
    rules = COMPATIBILITY_RULES
    if complete:
        rules = rules + COMPLETENESS_RULES
    issues: list[Issue] = []
    for rule in rules:
        issues.extend(rule(build))
    return issues