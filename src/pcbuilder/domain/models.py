from enum import StrEnum

from pydantic import BaseModel, model_validator


class ComponentType(StrEnum):
    CPU = "CPU"
    GPU = "GPU"
    RAM = "RAM"
    STORAGE = "STORAGE"
    MOTHERBOARD = "MOTHERBOARD"
    POWER_SUPPLY = "POWER_SUPPLY"
    CASE = "CASE"
    COOLING = "COOLING"


class MemoryType(StrEnum):
    DDR3 = "ddr3"
    DDR4 = "ddr4"
    DDR5 = "ddr5"


class Component(BaseModel):
    id: str
    category: ComponentType
    brand: str
    model: str
    mpn: str | None = None  # код производителя — для матчинга между магазинами
    ean: str | None = None  # штрихкод, та же цель

    @property
    def name(self) -> str:
        return f"{self.brand} {self.model}"


class CPU(Component):
    category: ComponentType = ComponentType.CPU
    socket: str  # "AM5", "LGA1700"
    tdp_w: int  # Thermal Design Power
    memory_types: list[MemoryType]
    integrated_graphics: bool = False
    includes_cooler: bool = False
    cores: int
    threads: int
    base_clock_mhz: int | None = None
    boost_clock_mhz: int | None = None


class MotherBoardFormFactor(StrEnum):
    ATX = "ATX"
    MICRO_ATX = "Micro-ATX"
    MINI_ITX = "Mini-ITX"
    E_ATX = "E-ATX"


class Motherboard(Component):
    category: ComponentType = ComponentType.MOTHERBOARD
    socket: str
    memory_type: MemoryType
    form_factor: MotherBoardFormFactor
    chipset: str
    max_memory_gb: int
    memory_slots: int
    sata_ports: int = 0
    m2_slots: int = 0


class RamKit(Component):
    category: ComponentType = ComponentType.RAM
    memory_type: MemoryType
    capacity_gb: int  # суммарно на комплект
    speed_mhz: int
    modules: int  # количество планок в комплекте
    cas_latency: int | None = None


class Gpu(Component):
    category: ComponentType = ComponentType.GPU
    vram_gb: int
    tdp_w: int
    length_mm: float
    power_connectors: list[str]
    recommended_psu_w: int | None = None


class StorageFormFactor(StrEnum):
    M2 = "m.2"
    INCH_2_5 = "2.5"
    INCH_3_5 = "3.5"


class StorageInterface(StrEnum):
    SATA = "SATA"
    NVME = "NVMe"


class StorageType(StrEnum):
    HDD = "HDD"
    SSD = "SSD"


class Storage(Component):
    category: ComponentType = ComponentType.STORAGE
    capacity_gb: int
    form_factor: StorageFormFactor
    interface: StorageInterface
    read_mb_s: int | None = None  # для ранжирования
    write_mb_s: int | None = None
    storage_type: StorageType

    @model_validator(mode="after")
    def check_combination(self):
        if (
            self.interface == StorageInterface.NVME
            and self.form_factor != StorageFormFactor.M2
        ):
            raise ValueError("NVMe бывает только в форм-факторе M.2")
        if (
            self.storage_type == StorageType.HDD
            and self.form_factor == StorageFormFactor.M2
        ):
            raise ValueError("HDD не бывает в форм-факторе M.2")
        return self

    @property
    def kind(self) -> str:
        if self.storage_type == StorageType.HDD:
            return "HDD"
        if self.interface == StorageInterface.NVME:
            return "NVMe SSD"
        return "SATA SSD"


class PsuFormFactor(StrEnum):
    ATX = "ATX"
    SFX = "SFX"
    SFX_L = "SFX-L"


class PowerSupply(Component):
    category: ComponentType = ComponentType.POWER_SUPPLY
    wattage_w: int
    efficiency_rating: str | None = None  # "80 Plus Bronze", "80 Plus Gold"
    modular: bool = False
    form_factor: PsuFormFactor | None = PsuFormFactor.ATX
    pcie_8pin: int = 0
    has_12vhpwr: bool = False
    length_mm: int | None = None


class Cooling(Component):
    category: ComponentType = ComponentType.COOLING
    sockets: list[str]
    height_mm: int | None = None
    radiator_mm: int | None = None
    max_tdp_w: int | None = None


class Case(Component):
    category: ComponentType = ComponentType.CASE
    supported_motherboard_form_factors: list[
        MotherBoardFormFactor
    ]  # какие платы влезают
    max_gpu_length_mm: int
    max_cooler_height_mm: int
    psu_form_factors: list[PsuFormFactor] = [PsuFormFactor.ATX]
    max_psu_length_mm: int | None = None


class Build(BaseModel):
    cpu: CPU | None = None
    motherboard: Motherboard | None = None
    ram: RamKit | None = None
    gpu: Gpu | None = None
    storage: list[Storage] = []
    psu: PowerSupply | None = None
    case: Case | None = None
    cooling: Cooling | None = None
