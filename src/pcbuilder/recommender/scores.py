"""Performance scores: how much faster one part is than another.

IMPORTANT: these are rough estimates, not benchmark results. They let the solver
compare options and are good enough for that — the orders of magnitude are right. But
before relying on them, replace them with benchmark data (TechPowerUp relative
performance for GPUs, PassMark / Cinebench for CPUs).
"""

from collections.abc import Mapping
from dataclasses import dataclass

from pcbuilder.domain.models import CPU, GPU

# Relative gaming performance of GPUs, RTX 4090 = 100.
# Approximate: 1440p/4K rasterization, orders of magnitude from aggregate reviews.
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

# Relative per-clock gaming speed of each architecture (Zen 4 = 1.0). Approximate.
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

X3D_GAMING_BONUS = 1.25  # 3D V-Cache: the large cache noticeably speeds up games

# To make CPU and GPU scores comparable, both scales are normalized to 0–100:
# for GPUs 100 is the RTX 4090, for CPUs 100 is the raw score of the reference CPU.
CPU_GAMING_REFERENCE = 140.0  # ≈ Ryzen 7 9800X3D
CPU_MULTICORE_REFERENCE = 98.0  # ≈ 16-core Zen 5


def _ipc(cpu: CPU) -> float:
    return ARCHITECTURE_IPC.get(cpu.architecture or "", UNKNOWN_ARCHITECTURE_IPC)


def _boost_ghz(cpu: CPU) -> float:
    return (cpu.boost_clock_mhz or cpu.base_clock_mhz or 4000) / 1000


def cpu_gaming_index(cpu: CPU) -> float:
    """CPU gaming score, 0–100. Games use the first ~8 cores; beyond that the gain is nearly zero."""
    cores_factor = 0.7 + 0.3 * min(cpu.cores, 8) / 8
    raw = _ipc(cpu) * _boost_ghz(cpu) * cores_factor * 20
    if "X3D" in cpu.model:
        raw *= X3D_GAMING_BONUS
    return round(100 * raw / CPU_GAMING_REFERENCE, 1)


def cpu_multicore_index(cpu: CPU) -> float:
    """Workstation score (rendering, compiling), 0–100: every core counts here."""
    raw = _ipc(cpu) * _boost_ghz(cpu) * cpu.cores
    return round(100 * raw / CPU_MULTICORE_REFERENCE, 1)


def gpu_index(gpu: GPU) -> float:
    """GPU gaming score, 0–100+ (RTX 4090 = 100)."""
    return GPU_PERFORMANCE.get(gpu.chipset, 0.0)


# --- Profiles ----------------------------------------------------------------------


@dataclass(frozen=True)
class GamingProfile:
    """Gaming: performance is set by the bottleneck.

    The CPU prepares each frame, then the GPU renders it. If one is slower, the other
    sits idle — so the build score is the minimum of the two, not the sum.
    As a result, the solver won't overpay for a CPU the GPU can't keep busy anyway,
    and vice versa.
    """

    name: str = "gaming"
    # How much "GPU" a CPU scoring 100 can keep fed.
    # 1.2: a top gaming CPU fully loads a GPU at level 120 (between the 4090 and 5090).
    cpu_feeds_gpu: float = 1.2

    def score(self, cpu: CPU, gpu: GPU) -> float:
        return min(gpu_index(gpu), cpu_gaming_index(cpu) * self.cpu_feeds_gpu)


@dataclass(frozen=True)
class WorkstationProfile:
    """Workstation: the CPU matters more, the GPU helps (render acceleration, video editing)."""

    name: str = "workstation"
    cpu_weight: float = 0.7
    gpu_weight: float = 0.3

    def score(self, cpu: CPU, gpu: GPU) -> float:
        return self.cpu_weight * cpu_multicore_index(cpu) + self.gpu_weight * gpu_index(
            gpu
        )


Profile = GamingProfile | WorkstationProfile

GAMING = GamingProfile()
WORKSTATION = WorkstationProfile()
