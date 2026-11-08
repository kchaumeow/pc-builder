from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, model_validator

# --- Reference values ----------------------------------------------------------


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
    DDR2 = "ddr2"
    DDR3 = "ddr3"
    DDR4 = "ddr4"
    DDR5 = "ddr5"


class MotherBoardFormFactor(StrEnum):
    ATX = "ATX"
    MICRO_ATX = "Micro-ATX"
    MINI_ITX = "Mini-ITX"
    E_ATX = "E-ATX"


class StorageMedia(StrEnum):
    HDD = "hdd"
    SSD = "ssd"


class StorageFormFactor(StrEnum):
    M2 = "m.2"
    INCH_2_5 = "2.5"
    INCH_3_5 = "3.5"


class StorageInterface(StrEnum):
    SATA = "SATA"
    NVME = "NVMe"


class PsuFormFactor(StrEnum):
    ATX = "ATX"
    SFX = "SFX"
    SFX_L = "SFX-L"


class PsuModularity(StrEnum):
    FULL = "full"
    SEMI = "semi"
    NONE = "none"


class PsuEfficiency(StrEnum):
    # Declaration order = quality order, worst to best
    PLUS = "80 Plus"
    BRONZE = "80 Plus Bronze"
    SILVER = "80 Plus Silver"
    GOLD = "80 Plus Gold"
    PLATINUM = "80 Plus Platinum"
    TITANIUM = "80 Plus Titanium"


# --- Parts ---------------------------------------------------------------------


class Component(BaseModel):
    id: str
    category: ComponentType
    brand: str
    model: str
    mpn: str | None = None  # manufacturer part number, for matching across shops
    ean: str | None = None  # barcode, same purpose

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
    architecture: str | None = None  # "Zen 4", "Raptor Lake"
    threads: int | None = (
        None  # not in the dataset; "cores x 2" is wrong for Intel 12th gen+
    )
    base_clock_mhz: int | None = None
    boost_clock_mhz: int | None = None


class Motherboard(Component):
    category: ComponentType = ComponentType.MOTHERBOARD
    socket: str
    chipset: str
    form_factor: MotherBoardFormFactor
    memory_type: MemoryType
    memory_slots: int
    max_memory_gb: int
    # None means "unknown" (not in the dataset), 0 means "known: none"
    sata_ports: int | None = None
    m2_slots: int | None = None


class RamKit(Component):
    category: ComponentType = ComponentType.RAM
    memory_type: MemoryType
    capacity_gb: int  # total for the kit
    modules: int  # number of modules in the kit
    speed_mhz: int
    cas_latency: int | None = None  # in clock cycles


class GPU(Component):
    category: ComponentType = ComponentType.GPU
    chipset: str  # "GeForce RTX 4070", "Radeon RX 9070 XT"
    vram_gb: int
    tdp_w: int
    length_mm: int
    # ["8-pin", "8-pin"] or ["12VHPWR"]. None means unknown: connectors are chosen by the card maker
    power_connectors: list[str] | None = None
    recommended_psu_w: int | None = None  # recommendation for the whole system


class Storage(Component):
    category: ComponentType = ComponentType.STORAGE
    capacity_gb: int
    media: StorageMedia
    form_factor: StorageFormFactor  # decides which port is used: M.2 slot or SATA
    interface: StorageInterface
    read_mb_s: int | None = None  # for ranking
    write_mb_s: int | None = None

    @model_validator(mode="after")
    def check_combination(self):
        if (
            self.interface == StorageInterface.NVME
            and self.form_factor != StorageFormFactor.M2
        ):
            raise ValueError("NVMe is only available in the M.2 form factor")
        if self.media == StorageMedia.HDD and self.form_factor == StorageFormFactor.M2:
            raise ValueError("HDDs do not come in the M.2 form factor")
        return self

    @property
    def kind(self) -> str:
        if self.media == StorageMedia.HDD:
            return "HDD"
        if self.interface == StorageInterface.NVME:
            return "NVMe SSD"
        return "SATA SSD"


class PowerSupply(Component):
    category: ComponentType = ComponentType.POWER_SUPPLY
    wattage_w: int
    efficiency: PsuEfficiency | None = None
    modularity: PsuModularity | None = None
    form_factor: PsuFormFactor = PsuFormFactor.ATX
    length_mm: int | None = None
    # None means "unknown", 0 / False means "known: none"
    pcie_8pin: int | None = None
    has_12vhpwr: bool | None = None


class Cooling(Component):
    category: ComponentType = ComponentType.COOLING
    sockets: list[str]
    height_mm: int | None = None  # tower coolers; None for AIOs
    radiator_mm: int | None = None  # AIOs: 120 / 240 / 360
    max_tdp_w: int | None = None


class Case(Component):
    category: ComponentType = ComponentType.CASE
    supported_motherboard_form_factors: list[MotherBoardFormFactor]
    max_gpu_length_mm: int
    max_cooler_height_mm: int
    psu_form_factors: list[PsuFormFactor] = [PsuFormFactor.ATX]
    max_psu_length_mm: int | None = None


# --- Build ---------------------------------------------------------------------


class Build(BaseModel):
    """All fields are optional: a build is assembled part by part."""

    cpu: CPU | None = None
    motherboard: Motherboard | None = None
    ram: RamKit | None = None
    gpu: GPU | None = None
    storage: list[Storage] = []
    psu: PowerSupply | None = None
    case: Case | None = None
    cooling: Cooling | None = None


# --- Offers --------------------------------------------------------------------


class Offer(BaseModel):
    """Price of a part from a specific source. A part holds specs that never change;
    an offer holds price and availability, which change daily and differ between shops."""

    part_id: str
    source: str  # "docyx", later "geizhals", "mindfactory"...
    price: Decimal  # money is not a float: 0.1 + 0.2 != 0.3
    currency: str = "USD"
