from enum import Enum

from pydantic import BaseModel

from pcbuilder.domain.models import Build


class Severity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class Issue(BaseModel):
    severity: Severity
    rule: str  # короткий код правила
    message: str  # текст для человека


def _error(rule: str, message: str) -> Issue:
    return Issue(severity=Severity.ERROR, rule=rule, message=message)


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
