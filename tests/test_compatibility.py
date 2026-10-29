from pcbuilder.domain.compatibility import (
    Severity,
    check,
    cooler_fits_case,
    cooler_handles_tdp,
    cooler_supports_cpu,
    cpu_has_cooling,
    cpu_socket_matches_motherboard,
    estimated_power_w,
    gpu_fits_case,
    has_graphics_output,
    motherboard_fits_case,
    psu_fits_case,
    psu_has_gpu_connectors,
    psu_wattage_sufficient,
    ram_matches_cpu,
    ram_matches_motherboard,
    storage_fits_motherboard,
)
from pcbuilder.domain.models import (
    CPU,
    GPU,
    Build,
    Case,
    Cooling,
    MemoryType,
    Motherboard,
    MotherBoardFormFactor,
    PsuFormFactor,
    RamKit,
    Storage,
    StorageFormFactor,
    StorageInterface,
    StorageMedia,
)
from pcbuilder.domain.models import PowerSupply as PSU

# --- Фабрики -----------------------------------------------------------------------
# Параметры — только то, что тесты меняют. Дефолты нейтральные:
# все фабрики вместе дают совместимую сборку без единой претензии.


def make_cpu(
    socket: str = "AM5",
    memory_types: list[MemoryType] | None = None,
    tdp_w: int = 65,
    includes_cooler: bool = True,
    integrated_graphics: bool = True,
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
        includes_cooler=includes_cooler,
        integrated_graphics=integrated_graphics,
    )


def make_motherboard(
    socket: str = "AM5",
    memory_type: MemoryType = MemoryType.DDR5,
    memory_slots: int = 4,
    max_memory_gb: int = 192,
    form_factor: MotherBoardFormFactor = MotherBoardFormFactor.MICRO_ATX,
    m2_slots: int = 2,
    sata_ports: int = 4,
) -> Motherboard:
    return Motherboard(
        id="mb-1",
        brand="MSI",
        model="B650M",
        socket=socket,
        chipset="B650",
        form_factor=form_factor,
        memory_type=memory_type,
        memory_slots=memory_slots,
        max_memory_gb=max_memory_gb,
        m2_slots=m2_slots,
        sata_ports=sata_ports,
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


def make_psu(
    wattage_w: int = 750,
    pcie_8pin: int = 2,
    has_12vhpwr: bool = False,
    form_factor: PsuFormFactor = PsuFormFactor.ATX,
    length_mm: int | None = None,
) -> PSU:
    return PSU(
        id="psu-1",
        brand="Corsair",
        model="RM750x",
        wattage_w=wattage_w,
        pcie_8pin=pcie_8pin,
        has_12vhpwr=has_12vhpwr,
        form_factor=form_factor,
        length_mm=length_mm,
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


def make_case(
    supported_motherboard_form_factors: list[MotherBoardFormFactor] | None = None,
    max_gpu_length_mm: int = 360,
    max_cooler_height_mm: int = 170,
    psu_form_factors: list[PsuFormFactor] | None = None,
    max_psu_length_mm: int | None = None,
) -> Case:
    return Case(
        id="case-1",
        brand="Fractal",
        model="Pop Air",
        supported_motherboard_form_factors=supported_motherboard_form_factors
        or [MotherBoardFormFactor.ATX, MotherBoardFormFactor.MICRO_ATX, MotherBoardFormFactor.MINI_ITX],
        max_gpu_length_mm=max_gpu_length_mm,
        max_cooler_height_mm=max_cooler_height_mm,
        psu_form_factors=psu_form_factors or [PsuFormFactor.ATX],
        max_psu_length_mm=max_psu_length_mm,
    )


def make_cooling(
    height_mm: int | None = 155,
    sockets: list[str] | None = None,
    max_tdp_w: int | None = None,
) -> Cooling:
    return Cooling(
        id="cooler-1",
        brand="Thermalright",
        model="Peerless Assassin 120",
        sockets=sockets or ["AM5", "AM4", "LGA1700"],
        height_mm=height_mm,
        max_tdp_w=max_tdp_w,
    )


def make_storage(
    form_factor: StorageFormFactor = StorageFormFactor.M2,
    interface: StorageInterface = StorageInterface.NVME,
    media: StorageMedia = StorageMedia.SSD,
) -> Storage:
    return Storage(
        id="ssd-1",
        brand="WD",
        model="SN770 1TB",
        capacity_gb=1000,
        form_factor=form_factor,
        interface=interface,
        media=media,
    )


def make_good_build(**overrides) -> Build:
    """Полностью совместимая сборка; любую деталь можно подменить."""
    build = Build(
        cpu=make_cpu(),
        motherboard=make_motherboard(),
        ram=make_ram(),
        gpu=make_gpu(),
        storage=[make_storage()],
        psu=make_psu(),
        case=make_case(),
        cooling=make_cooling(),
    )
    return build.model_copy(update=overrides)

def rules(issues) -> set[str]:
    """Коды сработавших правил — чтобы сравнивать без учёта порядка."""
    return {issue.rule for issue in issues}


# --- Сокет CPU ↔ плата -------------------------------------------------------------


def test_socket_match_is_ok():
    build = Build(cpu=make_cpu(socket="AM5"), motherboard=make_motherboard(socket="AM5"))
    assert cpu_socket_matches_motherboard(build) == []


def test_socket_mismatch_is_error():
    build = Build(cpu=make_cpu(socket="AM5"), motherboard=make_motherboard(socket="LGA1700"))
    assert rules(cpu_socket_matches_motherboard(build)) == {"CPU_SOCKET_MISMATCH"}


def test_socket_rule_silent_without_motherboard():
    build = Build(cpu=make_cpu())
    assert cpu_socket_matches_motherboard(build) == []


# --- Память ↔ плата ----------------------------------------------------------------


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
    build = Build(motherboard=make_motherboard(memory_slots=2), ram=make_ram(modules=4))
    assert rules(ram_matches_motherboard(build)) == {"RAM_MODULES_EXCEEDS_SLOTS"}


def test_ram_capacity_exceeds_motherboard_limit_is_error():
    build = Build(motherboard=make_motherboard(max_memory_gb=32), ram=make_ram(capacity_gb=64))
    assert rules(ram_matches_motherboard(build)) == {"RAM_CAPACITY_EXCEEDS_MOTHERBOARD_LIMIT"}


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


# --- Память ↔ процессор ------------------------------------------------------------


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


# --- Мощность БП -------------------------------------------------------------------
# Фабрики по умолчанию: CPU 65 + GPU 200 + база 75 = 340 Вт; ×1.25 → 425 Вт


def test_estimated_power():
    build = Build(cpu=make_cpu(), gpu=make_gpu())
    assert estimated_power_w(build) == 340


def test_psu_exactly_at_requirement_is_ok():
    build = Build(cpu=make_cpu(), gpu=make_gpu(), psu=make_psu(wattage_w=425))
    assert psu_wattage_sufficient(build) == []


def test_psu_one_watt_short_is_error():
    build = Build(cpu=make_cpu(), gpu=make_gpu(), psu=make_psu(wattage_w=424))
    issues = psu_wattage_sufficient(build)
    assert rules(issues) == {"PSU_WATTAGE_INSUFFICIENT"}
    assert issues[0].severity == Severity.ERROR


def test_psu_without_gpu_needs_less_power():
    # 75 + 65 = 140 Вт; ×1.25 → 175 Вт
    build = Build(cpu=make_cpu(), psu=make_psu(wattage_w=175))
    assert psu_wattage_sufficient(build) == []


def test_psu_below_gpu_recommendation_is_warning():
    build = Build(
        cpu=make_cpu(),
        gpu=make_gpu(recommended_psu_w=650),
        psu=make_psu(wattage_w=550),
    )
    issues = psu_wattage_sufficient(build)
    assert rules(issues) == {"PSU_BELOW_GPU_RECOMMENDATION"}
    assert issues[0].severity == Severity.WARNING


def test_psu_below_requirement_and_recommendation_reports_both():
    build = Build(
        cpu=make_cpu(),
        gpu=make_gpu(recommended_psu_w=650),
        psu=make_psu(wattage_w=400),
    )
    assert rules(psu_wattage_sufficient(build)) == {
        "PSU_WATTAGE_INSUFFICIENT",
        "PSU_BELOW_GPU_RECOMMENDATION",
    }


def test_psu_wattage_rule_silent_without_psu():
    build = Build(cpu=make_cpu(), gpu=make_gpu())
    assert psu_wattage_sufficient(build) == []


# --- Разъёмы БП --------------------------------------------------------------------


def test_psu_enough_8pin_is_ok():
    build = Build(psu=make_psu(pcie_8pin=2), gpu=make_gpu(power_connectors=["8-pin", "8-pin"]))
    assert psu_has_gpu_connectors(build) == []


def test_psu_3_8pin_connectors_insufficient_is_error():
    build = Build(
        psu=make_psu(pcie_8pin=2),
        gpu=make_gpu(power_connectors=["8-pin", "8-pin", "8-pin"]),
    )
    issues = psu_has_gpu_connectors(build)
    assert rules(issues) == {"PSU_INSUFFICIENT_8PIN_CONNECTORS"}
    assert issues[0].severity == Severity.ERROR


def test_psu_native_12vhpwr_is_ok():
    build = Build(psu=make_psu(has_12vhpwr=True), gpu=make_gpu(power_connectors=["12VHPWR"]))
    assert psu_has_gpu_connectors(build) == []


def test_psu_12vhpwr_via_adapter_is_warning():
    build = Build(
        psu=make_psu(pcie_8pin=2, has_12vhpwr=False),
        gpu=make_gpu(power_connectors=["12VHPWR"]),
    )
    issues = psu_has_gpu_connectors(build)
    assert rules(issues) == {"PSU_12VHPWR_VIA_ADAPTER"}
    assert issues[0].severity == Severity.WARNING


def test_psu_12vhpwr_no_cable_no_adapter_is_error():
    build = Build(
        psu=make_psu(pcie_8pin=1, has_12vhpwr=False),
        gpu=make_gpu(power_connectors=["12VHPWR"]),
    )
    issues = psu_has_gpu_connectors(build)
    assert rules(issues) == {"PSU_MISSING_12VHPWR_CONNECTOR"}
    assert issues[0].severity == Severity.ERROR


def test_psu_connectors_rule_silent_without_gpu():
    build = Build(psu=make_psu(pcie_8pin=0))
    assert psu_has_gpu_connectors(build) == []


# --- Плата ↔ корпус ----------------------------------------------------------------


def test_motherboard_fits_case_is_ok():
    build = Build(
        motherboard=make_motherboard(form_factor=MotherBoardFormFactor.ATX),
        case=make_case(supported_motherboard_form_factors=[MotherBoardFormFactor.ATX]),
    )
    assert motherboard_fits_case(build) == []


def test_motherboard_does_not_fit_case_is_error():
    build = Build(
        motherboard=make_motherboard(form_factor=MotherBoardFormFactor.ATX),
        case=make_case(
            supported_motherboard_form_factors=[
                MotherBoardFormFactor.MICRO_ATX,
                MotherBoardFormFactor.MINI_ITX,
            ]
        ),
    )
    issues = motherboard_fits_case(build)
    assert rules(issues) == {"MOTHERBOARD_DOES_NOT_FIT_CASE"}
    assert issues[0].severity == Severity.ERROR


def test_motherboard_case_rule_silent_without_case():
    assert motherboard_fits_case(Build(motherboard=make_motherboard())) == []


def test_motherboard_case_rule_silent_without_motherboard():
    assert motherboard_fits_case(Build(case=make_case())) == []


# --- Видеокарта ↔ корпус -----------------------------------------------------------


def test_gpu_exactly_at_case_limit_is_ok():
    build = Build(gpu=make_gpu(length_mm=320), case=make_case(max_gpu_length_mm=320))
    assert gpu_fits_case(build) == []


def test_gpu_one_mm_too_long_is_error():
    build = Build(gpu=make_gpu(length_mm=321), case=make_case(max_gpu_length_mm=320))
    issues = gpu_fits_case(build)
    assert rules(issues) == {"GPU_TOO_LONG_FOR_CASE"}
    assert issues[0].severity == Severity.ERROR


def test_gpu_case_rule_silent_without_case():
    assert gpu_fits_case(Build(gpu=make_gpu())) == []


def test_gpu_case_rule_silent_without_gpu():
    assert gpu_fits_case(Build(case=make_case())) == []


# --- Кулер ↔ корпус ----------------------------------------------------------------


def test_cooler_exactly_at_case_limit_is_ok():
    build = Build(cooling=make_cooling(height_mm=160), case=make_case(max_cooler_height_mm=160))
    assert cooler_fits_case(build) == []


def test_cooler_one_mm_too_tall_is_error():
    build = Build(cooling=make_cooling(height_mm=171), case=make_case(max_cooler_height_mm=170))
    issues = cooler_fits_case(build)
    assert rules(issues) == {"COOLER_TOO_TALL_FOR_CASE"}
    assert issues[0].severity == Severity.ERROR


def test_cooler_without_height_is_silent():
    # Водянка: у неё нет башни, ограничение по высоте неприменимо
    build = Build(cooling=make_cooling(height_mm=None), case=make_case(max_cooler_height_mm=100))
    assert cooler_fits_case(build) == []


def test_cooler_case_rule_silent_without_case():
    assert cooler_fits_case(Build(cooling=make_cooling())) == []


def test_cooler_case_rule_silent_without_cooler():
    assert cooler_fits_case(Build(case=make_case())) == []


# --- БП ↔ корпус -------------------------------------------------------------------


def test_psu_form_factor_supported_is_ok():
    build = Build(
        psu=make_psu(form_factor=PsuFormFactor.SFX),
        case=make_case(psu_form_factors=[PsuFormFactor.ATX, PsuFormFactor.SFX]),
    )
    assert psu_fits_case(build) == []


def test_psu_form_factor_not_supported_is_error():
    build = Build(
        psu=make_psu(form_factor=PsuFormFactor.ATX),
        case=make_case(psu_form_factors=[PsuFormFactor.SFX]),
    )
    issues = psu_fits_case(build)
    assert rules(issues) == {"PSU_FORM_FACTOR_NOT_SUPPORTED_BY_CASE"}
    assert issues[0].severity == Severity.ERROR


def test_psu_exactly_at_case_length_limit_is_ok():
    build = Build(psu=make_psu(length_mm=160), case=make_case(max_psu_length_mm=160))
    assert psu_fits_case(build) == []


def test_psu_one_mm_too_long_is_error():
    build = Build(psu=make_psu(length_mm=161), case=make_case(max_psu_length_mm=160))
    issues = psu_fits_case(build)
    assert rules(issues) == {"PSU_TOO_LONG_FOR_CASE"}
    assert issues[0].severity == Severity.ERROR


def test_psu_length_unchecked_when_case_limit_unknown():
    build = Build(psu=make_psu(length_mm=250), case=make_case(max_psu_length_mm=None))
    assert psu_fits_case(build) == []


def test_psu_case_reports_both_problems():
    build = Build(
        psu=make_psu(form_factor=PsuFormFactor.ATX, length_mm=180),
        case=make_case(psu_form_factors=[PsuFormFactor.SFX], max_psu_length_mm=160),
    )
    issues = psu_fits_case(build)
    assert rules(issues) == {"PSU_TOO_LONG_FOR_CASE", "PSU_FORM_FACTOR_NOT_SUPPORTED_BY_CASE"}
    assert all(issue.severity == Severity.ERROR for issue in issues)


def test_psu_case_rule_silent_without_case():
    assert psu_fits_case(Build(psu=make_psu())) == []


def test_psu_case_rule_silent_without_psu():
    assert psu_fits_case(Build(case=make_case())) == []


# --- Кулер ↔ процессор -------------------------------------------------------------


def test_cooler_supports_cpu_socket_is_ok():
    build = Build(cpu=make_cpu(socket="AM5"), cooling=make_cooling(sockets=["AM5", "AM4"]))
    assert cooler_supports_cpu(build) == []


def test_cooler_wrong_socket_is_error():
    build = Build(cpu=make_cpu(socket="LGA1851"), cooling=make_cooling(sockets=["AM5", "AM4"]))
    issues = cooler_supports_cpu(build)
    assert rules(issues) == {"COOLER_NOT_COMPATIBLE_WITH_CPU_SOCKET"}
    assert issues[0].severity == Severity.ERROR


def test_cooler_socket_rule_silent_without_cooler():
    assert cooler_supports_cpu(Build(cpu=make_cpu())) == []


def test_cooler_exactly_at_tdp_is_ok():
    build = Build(cpu=make_cpu(tdp_w=120), cooling=make_cooling(max_tdp_w=120))
    assert cooler_handles_tdp(build) == []


def test_cooler_tdp_too_low_is_warning():
    build = Build(cpu=make_cpu(tdp_w=170), cooling=make_cooling(max_tdp_w=150))
    issues = cooler_handles_tdp(build)
    assert rules(issues) == {"COOLER_TDP_TOO_LOW_FOR_CPU"}
    assert issues[0].severity == Severity.WARNING


def test_cooler_without_tdp_rating_is_silent():
    build = Build(cpu=make_cpu(tdp_w=250), cooling=make_cooling(max_tdp_w=None))
    assert cooler_handles_tdp(build) == []


# --- Накопители ↔ плата ------------------------------------------------------------


def test_storage_fits_motherboard_is_ok():
    build = Build(
        motherboard=make_motherboard(m2_slots=2, sata_ports=2),
        storage=[
            make_storage(),
            make_storage(),
            make_storage(StorageFormFactor.INCH_2_5, StorageInterface.SATA),
            make_storage(StorageFormFactor.INCH_3_5, StorageInterface.SATA, StorageMedia.HDD),
        ],
    )
    assert storage_fits_motherboard(build) == []


def test_too_many_m2_drives_is_error():
    build = Build(
        motherboard=make_motherboard(m2_slots=1),
        storage=[make_storage(), make_storage()],
    )
    issues = storage_fits_motherboard(build)
    assert rules(issues) == {"STORAGE_TOO_MANY_M2"}
    assert issues[0].severity == Severity.ERROR


def test_too_many_sata_drives_is_error():
    sata_ssd = make_storage(StorageFormFactor.INCH_2_5, StorageInterface.SATA)
    build = Build(
        motherboard=make_motherboard(sata_ports=4),
        storage=[sata_ssd] * 5,
    )
    assert rules(storage_fits_motherboard(build)) == {"STORAGE_TOO_MANY_SATA"}


def test_m2_sata_drive_uses_m2_slot_not_sata_port():
    # Crucial MX500 M.2: интерфейс SATA, но физически занимает M.2-слот
    m2_sata = make_storage(StorageFormFactor.M2, StorageInterface.SATA)
    build = Build(
        motherboard=make_motherboard(m2_slots=1, sata_ports=0),
        storage=[m2_sata],
    )
    assert storage_fits_motherboard(build) == []


def test_storage_rule_silent_without_drives():
    assert storage_fits_motherboard(Build(motherboard=make_motherboard())) == []


def test_storage_rule_silent_without_motherboard():
    assert storage_fits_motherboard(Build(storage=[make_storage()])) == []


# --- Правила полноты ---------------------------------------------------------------


def test_cpu_with_boxed_cooler_needs_no_cooler():
    build = Build(cpu=make_cpu(includes_cooler=True))
    assert cpu_has_cooling(build) == []


def test_cpu_without_any_cooling_is_error():
    build = Build(cpu=make_cpu(includes_cooler=False))
    assert rules(cpu_has_cooling(build)) == {"CPU_NO_COOLING"}


def test_separate_cooler_covers_missing_boxed_one():
    build = Build(cpu=make_cpu(includes_cooler=False), cooling=make_cooling())
    assert cpu_has_cooling(build) == []


def test_igpu_without_gpu_is_ok():
    build = Build(cpu=make_cpu(integrated_graphics=True))
    assert has_graphics_output(build) == []


def test_no_gpu_and_no_igpu_is_error():
    build = Build(cpu=make_cpu(integrated_graphics=False))
    assert rules(has_graphics_output(build)) == {"NO_GRAPHICS_OUTPUT"}


def test_graphics_rule_silent_without_cpu():
    assert has_graphics_output(Build()) == []


# --- check(): все правила вместе ---------------------------------------------------


def test_good_build_has_no_issues():
    # Самый важный тест: все фабрики вместе дают сборку без единой претензии
    assert check(make_good_build(), complete=True) == []


def test_empty_build_has_no_issues():
    assert check(Build()) == []


def test_partial_build_ignores_missing_cooler():
    build = Build(cpu=make_cpu(includes_cooler=False))
    assert check(build) == []


def test_complete_check_reports_missing_cooler_once():
    build = make_good_build(cpu=make_cpu(includes_cooler=False), cooling=None)
    issues = check(build, complete=True)
    # Список, а не множество: множество спрятало бы дубликат
    assert [issue.rule for issue in issues] == ["CPU_NO_COOLING"]


def test_check_collects_issues_from_several_rules():
    build = make_good_build(
        motherboard=make_motherboard(socket="LGA1700"),
        gpu=make_gpu(length_mm=400),
    )
    assert rules(check(build)) == {"CPU_SOCKET_MISMATCH", "GPU_TOO_LONG_FOR_CASE"}