import math
from collections.abc import Callable
from enum import StrEnum

from pydantic import BaseModel

from pcbuilder.domain.models import Build, StorageFormFactor

BASE_SYSTEM_POWER_W: int = 75  # motherboard, memory, drives, fans
PSU_HEADROOM: float = 1.25  # headroom for power spikes and PSU aging
ADAPTER_MIN_8PIN: int = 2  # a 12VHPWR adapter takes at least two 8-pin


class Severity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class Issue(BaseModel):
    severity: Severity
    rule: str  # short rule code
    message: str  # human-readable text


def _error(rule: str, message: str) -> Issue:
    return Issue(severity=Severity.ERROR, rule=rule, message=message)


def _warning(rule: str, message: str) -> Issue:
    return Issue(severity=Severity.WARNING, rule=rule, message=message)


def estimated_power_w(build: Build) -> int:
    """Estimated build power draw, without headroom."""
    total = BASE_SYSTEM_POWER_W
    if build.cpu:
        total += build.cpu.tdp_w
    if build.gpu:
        total += build.gpu.tdp_w
    return total


# --- Compatibility rules -----------------------------------------------------------
# Check for conflicts between parts already selected.
# If a part is missing they stay silent: the build is assembled step by step.


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
                f"{ram.memory_type.upper()} memory does not fit the motherboard: it needs {mb.memory_type.upper()}",
            )
        )
    if ram.modules > mb.memory_slots:
        issues.append(
            _error(
                "RAM_MODULES_EXCEEDS_SLOTS",
                f"{ram.modules} memory modules, but the motherboard has {mb.memory_slots} slots",
            )
        )
    if ram.capacity_gb > mb.max_memory_gb:
        issues.append(
            _error(
                "RAM_CAPACITY_EXCEEDS_MOTHERBOARD_LIMIT",
                f"{ram.capacity_gb} GB of memory, but the motherboard supports up to {mb.max_memory_gb} GB",
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
                f"CPU does not support {ram.memory_type.upper()} memory (supports: {', '.join(t.upper() for t in cpu.memory_types)})",
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
                f"A {psu.wattage_w} W power supply is not enough: {required_power} W needed with headroom",
            )
        )
    if (
        gpu
        and gpu.recommended_psu_w is not None
        and psu.wattage_w < gpu.recommended_psu_w
    ):
        issues.append(
            _warning(
                "PSU_BELOW_GPU_RECOMMENDATION",
                f"{psu.wattage_w} W power supply is below the graphics card maker's recommendation of {gpu.recommended_psu_w} W",
            )
        )
    return issues


def psu_has_gpu_connectors(build: Build) -> list[Issue]:
    issues: list[Issue] = []
    if not (build.psu and build.gpu):
        return issues

    if build.gpu.power_connectors is None:  # card connectors unknown, nothing to check
        return issues

    psu, gpu = build.psu, build.gpu
    gpu_8_pin_connectors = gpu.power_connectors.count("8-pin")
    needs_12vhpwr = "12VHPWR" in gpu.power_connectors

    # Check the 8-pin count only when known. 0 means "definitely none", not "unknown".
    if psu.pcie_8pin is not None and gpu_8_pin_connectors > psu.pcie_8pin:
        issues.append(
            _error(
                "PSU_INSUFFICIENT_8PIN_CONNECTORS",
                f"Graphics card needs {gpu_8_pin_connectors} 8-pin connectors, the power supply has {psu.pcie_8pin}",
            )
        )

    # Only a known "no" (False). None means unknown, so skip the check.
    if needs_12vhpwr and psu.has_12vhpwr is False:
        if psu.pcie_8pin is not None and psu.pcie_8pin < ADAPTER_MIN_8PIN:
            issues.append(
                _error(
                    "PSU_MISSING_12VHPWR_CONNECTOR",
                    f"Graphics card needs a 12VHPWR connector; the power supply has none and too few 8-pin for an adapter: {psu.pcie_8pin}",
                )
            )
        else:
            issues.append(
                _warning(
                    "PSU_12VHPWR_VIA_ADAPTER",
                    "Graphics card needs a 12VHPWR connector; the power supply has none, so an adapter is required",
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
                f"{mb.form_factor} motherboard does not fit the case "
                f"(supported: {', '.join(case.supported_motherboard_form_factors)})",
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
                f"Graphics card is {gpu.length_mm} mm long, the case fits up to {case.max_gpu_length_mm} mm",
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
                f"CPU cooler is {cooler.height_mm} mm tall, the case fits up to {case.max_cooler_height_mm} mm",
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
                f"{psu.form_factor} power supply does not fit the case "
                f"(supported: {', '.join(case.psu_form_factors)})",
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
                f"Power supply is {psu.length_mm} mm long, the case fits up to {case.max_psu_length_mm} mm",
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
                f"CPU cooler does not support socket {cpu.socket} (supports: {', '.join(cooler.sockets)})",
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
                f"CPU cooler is rated for {cooler.max_tdp_w} W, but the CPU TDP is {cpu.tdp_w} W",
            )
        ]
    return []


def storage_fits_motherboard(build: Build) -> list[Issue]:
    issues: list[Issue] = []
    if not (build.storage and build.motherboard):
        return issues

    mb = build.motherboard
    # The port is determined by form factor: M.2 (even with a SATA interface) takes an M.2 slot,
    # 2.5" and 3.5" drives connect to SATA ports.
    m2_count = sum(1 for s in build.storage if s.form_factor == StorageFormFactor.M2)
    sata_count = len(build.storage) - m2_count

    # Check only what is known: dataset motherboards have unknown slot and port counts (None)
    if mb.m2_slots is not None and m2_count > mb.m2_slots:
        issues.append(
            _error(
                "STORAGE_TOO_MANY_M2",
                f"{m2_count} M.2 drives, but the motherboard has {mb.m2_slots} M.2 slots",
            )
        )
    if mb.sata_ports is not None and sata_count > mb.sata_ports:
        issues.append(
            _error(
                "STORAGE_TOO_MANY_SATA",
                f"{sata_count} SATA drives, but the motherboard has {mb.sata_ports} SATA ports",
            )
        )
    return issues


# --- Completeness rules ------------------------------------------------------------
# Triggered by a MISSING part, so they apply only to a finished build.


def cpu_has_cooling(build: Build) -> list[Issue]:
    if not build.cpu:
        return []
    if not build.cooling and not build.cpu.includes_cooler:
        return [
            _error(
                "CPU_NO_COOLING",
                f"CPU {build.cpu.name} has no boxed cooler and no CPU cooler is selected",
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
                "No graphics card selected and the CPU has no integrated graphics",
            )
        ]
    return []


# --- Running -----------------------------------------------------------------------

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
    """Check a build.

    complete=False: while picking parts, only conflicts between selected parts.
    complete=True:  finished build, plus checks for missing parts.
    """
    rules = COMPATIBILITY_RULES
    if complete:
        rules = rules + COMPLETENESS_RULES
    issues: list[Issue] = []
    for rule in rules:
        issues.extend(rule(build))
    return issues
