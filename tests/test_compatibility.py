from pcbuilder.domain.compatibility import (
    Severity,
    cpu_socket_matches_motherboard,
    psu_has_gpu_connectors,
    psu_wattage_sufficient,
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
    PowerSupply as PSU,
    GPU,
)

# --- Фабрики -----------------------------------------------------------------
# Параметры — только то, что тесты меняют. Остальное — правдоподобные значения.


def make_cpu(
    socket: str = "AM5",
    memory_types: list[MemoryType] | None = None,
    tdp_w: int = 65,
) -> CPU:
    return CPU(
        id="cpu-1",
        brand="AMD",
        model="Ryzen 5 7600",
        socket=socket,
        tdp_w=tdp_w,
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

def make_psu(wattage_w: int = 750, pcie_8pin: int = 2, has_12vhpwr: bool = False) -> PSU:
    return PSU(
        id="psu-1",
        brand="Corsair",
        model="RM750x",
        wattage_w=wattage_w,
        pcie_8pin=pcie_8pin,
        has_12vhpwr=has_12vhpwr,
    )

def make_gpu(
    tdp_w: int = 200,
    power_connectors: list[str] | None = None,
    recommended_psu_w: int | None = None,
    length_mm: int = 285,
) -> GPU:
    return GPU(
        id="gpu-1",
        brand="NVIDIA",
        model="RTX 4070",
        tdp_w=tdp_w,
        recommended_psu_w=recommended_psu_w,
        power_connectors=power_connectors or ["8-pin", "8-pin"],
        vram_gb=12,
        length_mm=length_mm,
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

def test_psu_exactly_at_requirement_is_ok():

    build = Build(
        psu=make_psu(wattage_w=425),
        cpu=make_cpu(),
        gpu=make_gpu(tdp_w=200),
    )
    assert psu_wattage_sufficient(build) == []

def test_psu_one_watt_short_is_error():
    build = Build(cpu=make_cpu(), gpu=make_gpu(), psu=make_psu(wattage_w=424))
    issues = psu_wattage_sufficient(build)
    assert rules(issues) == {"PSU_WATTAGE_INSUFFICIENT"}
    assert issues[0].severity == Severity.ERROR

def test_psu_below_gpu_recommendation_is_warning():
    build = Build(
        cpu=make_cpu(),
        gpu=make_gpu(recommended_psu_w=650),
        psu=make_psu(wattage_w=550),
    )
    issues = psu_wattage_sufficient(build)
    assert rules(issues) == {"PSU_BELOW_GPU_RECOMMENDATION"}
    assert issues[0].severity == Severity.WARNING

def test_psu_3_8pin_connectors_insufficient_is_error():
    build = Build(
        psu=make_psu(wattage_w=750, pcie_8pin=2),
        gpu=make_gpu(power_connectors=["8-pin", "8-pin", "8-pin"]),
    )
    issues = psu_has_gpu_connectors(build)
    assert rules(issues) == {"PSU_INSUFFICIENT_8PIN_CONNECTORS"}
    assert issues[0].severity == Severity.ERROR

def test_psu_12vhpwr_connector_missing_is_warning():
    build = Build(
        psu=make_psu(wattage_w=750, pcie_8pin=2, has_12vhpwr=False),
        gpu=make_gpu(power_connectors=["12VHPWR"]),
    )
    issues = psu_has_gpu_connectors(build)
    assert rules(issues) == {"PSU_12VHPWR_VIA_ADAPTER"}
    assert issues[0].severity == Severity.WARNING

def test_psu_12vhpwr_connector_missing_is_error():
    build = Build(
        psu=make_psu(wattage_w=750, pcie_8pin=1, has_12vhpwr=False),
        gpu=make_gpu(power_connectors=["12VHPWR"]),
    )
    issues = psu_has_gpu_connectors(build)
    assert rules(issues) == {"PSU_MISSING_12VHPWR_CONNECTOR"}
    assert issues[0].severity == Severity.ERROR