from enum import StrEnum
import math

from pydantic import BaseModel

from pcbuilder.domain.models import Build


BASE_SYSTEM_POWER_W : int = 75   # плата, память, диски, вентиляторы
PSU_HEADROOM : float = 1.25        # запас: пики потребления, старение БП
ADAPTER_MIN_8PIN = 2


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
    total = BASE_SYSTEM_POWER_W
    if build.cpu:
        total += build.cpu.tdp_w
    if build.gpu:
        total += build.gpu.tdp_w
    return total
    

# rules of compatibility


def cpu_socket_matches_motherboard(build: Build) -> list[Issue]:
    issues: list[Issue] = []
    if not (build.cpu and build.motherboard):
        return issues
    if build.cpu.socket != build.motherboard.socket:
        return [
            _error(
                "CPU_SOCKET_MISMATCH",
                f"CPU socket {build.cpu.socket} does not match motherboard socket {build.motherboard.socket}",
            )
        ]
    return issues


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
    issues: list[Issue] = []
    if not (build.ram and build.cpu):
        return issues

    ram, cpu = build.ram, build.cpu

    if ram.memory_type not in cpu.memory_types:
        issues.append(
            _error(
                "RAM_MEMORY_TYPE_NOT_SUPPORTED_BY_CPU",
                f"RAM memory type {ram.memory_type} is not supported by CPU (supports: {', '.join(cpu.memory_types)})",
            )
        )
    return issues

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

    if gpu and gpu.recommended_psu_w and psu.wattage_w < gpu.recommended_psu_w:
        issues.append(_warning(
            "PSU_BELOW_GPU_RECOMMENDATION",
            f"PSU {psu.wattage_w}W is below GPU manufacturer recommendation {gpu.recommended_psu_w}W",
        ))

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
            issues.append(_error(
                "PSU_MISSING_12VHPWR_CONNECTOR",
                f"GPU requires 12VHPWR; PSU has no native cable and only {psu.pcie_8pin} 8-pin for an adapter",
            ))
        else:
            issues.append(_warning(
                "PSU_12VHPWR_VIA_ADAPTER",
                "GPU requires 12VHPWR; PSU has no native cable — an adapter will be needed",
            ))
    return issues