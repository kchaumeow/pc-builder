from pcbuilder.domain.compatibility import (
    cpu_socket_matches_motherboard,
    ram_matches_cpu,
    ram_matches_motherboard,
)
from pcbuilder.domain.models import (
    CPU,
    Build,
    MemoryType,
    Motherboard,
    MotherBoardFormFactor,
    RamKit,
)

# --- Фабрики -----------------------------------------------------------------
# Параметры — только то, что тесты меняют. Остальное — правдоподобные значения.


def make_cpu(
    socket: str = "AM5",
    memory_types: list[MemoryType] | None = None,
) -> CPU:
    return CPU(
        id="cpu-1",
        brand="AMD",
        model="Ryzen 5 7600",
        socket=socket,
        tdp_w=65,
        memory_types=memory_types or [MemoryType.DDR5],
        cores=6,
        threads=12,
    )


def make_motherboard(
    socket: str = "AM5",
    memory_type: MemoryType = MemoryType.DDR5,
    memory_slots: int = 4,
    max_memory_gb: int = 192,
) -> Motherboard:
    return Motherboard(
        id="mb-1",
        brand="MSI",
        model="B650M",
        socket=socket,
        chipset="B650",
        form_factor=MotherBoardFormFactor.MICRO_ATX,
        memory_type=memory_type,
        memory_slots=memory_slots,
        max_memory_gb=max_memory_gb,
    )


def make_ram(
    memory_type: MemoryType = MemoryType.DDR5,
    modules: int = 2,
    capacity_gb: int = 32,
) -> RamKit:
    return RamKit(
        id="ram-1",
        brand="Kingston",
        model="Fury Beast",
        memory_type=memory_type,
        modules=modules,
        capacity_gb=capacity_gb,
        speed_mhz=6000,
    )


def rules(issues) -> set[str]:
    """Коды сработавших правил — чтобы сравнивать без учёта порядка."""
    return {issue.rule for issue in issues}


# --- Сокет CPU ↔ плата -----------------------------------------------------------


def test_socket_match_is_ok():
    build = Build(
        cpu=make_cpu(socket="AM5"), motherboard=make_motherboard(socket="AM5")
    )
    assert cpu_socket_matches_motherboard(build) == []


def test_socket_mismatch_is_error():
    build = Build(
        cpu=make_cpu(socket="AM5"), motherboard=make_motherboard(socket="LGA1700")
    )
    assert rules(cpu_socket_matches_motherboard(build)) == {"CPU_SOCKET_MISMATCH"}


def test_socket_rule_silent_without_motherboard():
    build = Build(cpu=make_cpu())
    assert cpu_socket_matches_motherboard(build) == []


# --- Память ↔ плата -----------------------------------------------------------


def test_ram_matches_motherboard_is_ok():
    build = Build(motherboard=make_motherboard(), ram=make_ram())
    assert ram_matches_motherboard(build) == []


def test_ram_memory_type_mismatch_is_error():
    build = Build(
        motherboard=make_motherboard(memory_type=MemoryType.DDR5),
        ram=make_ram(memory_type=MemoryType.DDR4),
    )
    assert rules(ram_matches_motherboard(build)) == {"RAM_MEMORY_TYPE_MISMATCH"}


def test_ram_modules_exceeds_slots_is_error():
    build = Build(
        motherboard=make_motherboard(memory_slots=2),
        ram=make_ram(modules=4),
    )
    assert rules(ram_matches_motherboard(build)) == {"RAM_MODULES_EXCEEDS_SLOTS"}


def test_ram_capacity_exceeds_motherboard_limit_is_error():
    build = Build(
        motherboard=make_motherboard(max_memory_gb=32),
        ram=make_ram(capacity_gb=64),
    )
    assert rules(ram_matches_motherboard(build)) == {
        "RAM_CAPACITY_EXCEEDS_MOTHERBOARD_LIMIT"
    }


def test_ram_motherboard_reports_all_problems_at_once():
    build = Build(
        motherboard=make_motherboard(memory_type=MemoryType.DDR5, memory_slots=2),
        ram=make_ram(memory_type=MemoryType.DDR4, modules=4),
    )
    assert rules(ram_matches_motherboard(build)) == {
        "RAM_MEMORY_TYPE_MISMATCH",
        "RAM_MODULES_EXCEEDS_SLOTS",
    }


def test_ram_motherboard_rule_silent_without_motherboard():
    build = Build(ram=make_ram())
    assert ram_matches_motherboard(build) == []


# --- Память ↔ процессор ----------------------------------------------------------


def test_ram_supported_by_cpu_is_ok():
    build = Build(
        cpu=make_cpu(memory_types=[MemoryType.DDR5]),
        ram=make_ram(memory_type=MemoryType.DDR5),
    )
    assert ram_matches_cpu(build) == []


def test_ram_not_supported_by_cpu_is_error():
    build = Build(
        cpu=make_cpu(memory_types=[MemoryType.DDR5]),
        ram=make_ram(memory_type=MemoryType.DDR4),
    )
    assert rules(ram_matches_cpu(build)) == {"RAM_MEMORY_TYPE_NOT_SUPPORTED_BY_CPU"}


def test_cpu_with_two_memory_types_accepts_both():
    # Intel 12–14 поколения работают и с DDR4, и с DDR5
    cpu = make_cpu(socket="LGA1700", memory_types=[MemoryType.DDR4, MemoryType.DDR5])
    for memory_type in (MemoryType.DDR4, MemoryType.DDR5):
        build = Build(cpu=cpu, ram=make_ram(memory_type=memory_type))
        assert ram_matches_cpu(build) == []


def test_ram_cpu_rule_silent_without_cpu():
    build = Build(ram=make_ram())
    assert ram_matches_cpu(build) == []
