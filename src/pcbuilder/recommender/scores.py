"""Оценки производительности: насколько одна деталь быстрее другой.

ВАЖНО: это приблизительные оценки, а не результаты тестов. Они нужны, чтобы солвер
мог сравнивать варианты, и годятся для этого — порядок величин правильный. Но перед
тем как на них полагаться, их стоит заменить данными бенчмарков (TechPowerUp relative
performance для видеокарт, PassMark / Cinebench для процессоров).
"""

from collections.abc import Mapping
from dataclasses import dataclass

from pcbuilder.domain.models import CPU, GPU

# Относительная игровая производительность видеокарт, RTX 4090 = 100.
# Приблизительно: растеризация в 1440p/4K, по порядку величин из сводных обзоров.
GPU_PERFORMANCE: Mapping[str, float] = {
    # NVIDIA RTX 50
    "GeForce RTX 5090": 127,
    "GeForce RTX 5080": 81,
    "GeForce RTX 5070 Ti": 71,
    "GeForce RTX 5070": 56,
    "GeForce RTX 5060 Ti": 38,
    "GeForce RTX 5060": 32,
    "GeForce RTX 5050": 21,
    # NVIDIA RTX 40
    "GeForce RTX 4090": 100,
    "GeForce RTX 4080 SUPER": 73,
    "GeForce RTX 4080": 72,
    "GeForce RTX 4070 Ti SUPER": 63,
    "GeForce RTX 4070 Ti": 58,
    "GeForce RTX 4070 SUPER": 53,
    "GeForce RTX 4070": 45,
    "GeForce RTX 4060 Ti": 30,
    "GeForce RTX 4060": 25,
    # NVIDIA RTX 30
    "GeForce RTX 3090 Ti": 56,
    "GeForce RTX 3090": 50,
    "GeForce RTX 3080 Ti": 49,
    "GeForce RTX 3080 12GB": 47,
    "GeForce RTX 3080 10GB": 45,
    "GeForce RTX 3070 Ti": 38,
    "GeForce RTX 3070": 35,
    "GeForce RTX 3060 Ti": 31,
    "GeForce RTX 3060 12GB": 22,
    "GeForce RTX 3060 8GB": 19,
    "GeForce RTX 3050 8GB": 14,
    "GeForce RTX 3050 6GB": 10,
    # AMD RX 9000
    "Radeon RX 9070 XT": 70,
    "Radeon RX 9070": 62,
    "Radeon RX 9060 XT": 37,
    # AMD RX 7000
    "Radeon RX 7900 XTX": 75,
    "Radeon RX 7900 XT": 65,
    "Radeon RX 7900 GRE": 56,
    "Radeon RX 7800 XT": 50,
    "Radeon RX 7700 XT": 40,
    "Radeon RX 7600 XT": 27,
    "Radeon RX 7600": 26,
    # AMD RX 6000
    "Radeon RX 6950 XT": 50,
    "Radeon RX 6900 XT": 45,
    "Radeon RX 6800 XT": 43,
    "Radeon RX 6800": 38,
    "Radeon RX 6750 XT": 33,
    "Radeon RX 6700 XT": 30,
    "Radeon RX 6700": 26,
    "Radeon RX 6650 XT": 25,
    "Radeon RX 6600 XT": 23,
    "Radeon RX 6600": 20,
    "Radeon RX 6500 XT": 9,
    "Radeon RX 6400": 7,
    # Intel Arc
    "Arc B580": 27,
    "Arc B570": 23,
    "Arc A770": 23,
    "Arc A750": 21,
    "Arc A580": 19,
    "Arc A380": 7,
    "Arc A310": 5,
}

# Относительная скорость архитектуры на такт в играх (Zen 4 = 1.0). Приблизительно.
ARCHITECTURE_IPC: Mapping[str, float] = {
    "Zen 2": 0.70,
    "Zen 3": 0.85,
    "Zen 4": 1.00,
    "Zen 5": 1.08,
    "Alder Lake": 0.90,
    "Raptor Lake": 0.95,
    "Raptor Lake Refresh": 0.95,
    "Arrow Lake": 0.92,
}
UNKNOWN_ARCHITECTURE_IPC = 0.85

X3D_GAMING_BONUS = 1.25  # 3D V-Cache: большой кэш заметно ускоряет игры


def cpu_performance(cpu: CPU) -> float:
    """Грубая игровая оценка процессора: архитектура × частота × ядра, бонус за X3D.

    Для игр важны первые ~8 ядер; дальше прирост почти нулевой.
    """
    ipc = ARCHITECTURE_IPC.get(cpu.architecture or "", UNKNOWN_ARCHITECTURE_IPC)
    boost_ghz = (cpu.boost_clock_mhz or cpu.base_clock_mhz or 4000) / 1000
    cores_factor = 0.7 + 0.3 * min(cpu.cores, 8) / 8
    score = ipc * boost_ghz * cores_factor * 20  # ×20 — чтобы шкала была порядка 100
    if "X3D" in cpu.model:
        score *= X3D_GAMING_BONUS
    return round(score, 1)


def gpu_performance(gpu: GPU) -> float:
    return GPU_PERFORMANCE.get(gpu.chipset, 0.0)


@dataclass(frozen=True)
class Profile:
    """Для чего сборка: веса видеокарты и процессора в общей оценке."""

    name: str
    gpu_weight: float
    cpu_weight: float

    def score(self, cpu: CPU, gpu: GPU) -> float:
        return self.gpu_weight * gpu_performance(
            gpu
        ) + self.cpu_weight * cpu_performance(cpu)


GAMING = Profile("игры", gpu_weight=0.8, cpu_weight=0.2)
WORKSTATION = Profile("работа", gpu_weight=0.3, cpu_weight=0.7)
