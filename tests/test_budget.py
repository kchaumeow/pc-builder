from decimal import Decimal

import pytest

from pcbuilder.domain.models import Build
from pcbuilder.recommender.budget import best_build, cheapest_per_key
from pcbuilder.recommender.scores import (
    GAMING,
    WORKSTATION,
    GamingProfile,
    cpu_gaming_index,
    cpu_multicore_index,
    gpu_index,
)
from tests.test_compatibility import make_cpu, make_gpu
from tests.test_solver import BASE, named, priced

# Остальное из BASE стоит 150 + 100 + 80 + 90 + 70 + 30 = 520

CPU = make_cpu(includes_cooler=False).model_copy(update={"id": "cpu"})
FAST_GPU = named(make_gpu, "gpu-fast").model_copy(
    update={"chipset": "GeForce RTX 4080"}
)
SLOW_GPU = named(make_gpu, "gpu-slow").model_copy(
    update={"chipset": "GeForce RTX 4060"}
)


def catalog():
    return priced((CPU, "200"), (FAST_GPU, "900"), (SLOW_GPU, "300"), *BASE)


def test_gpu_index_known_and_unknown():
    assert gpu_index(FAST_GPU) > gpu_index(SLOW_GPU)
    unknown = FAST_GPU.model_copy(update={"chipset": "GeForce GTX 460"})
    assert gpu_index(unknown) == 0


def test_x3d_beats_same_cpu_without_cache():
    plain = make_cpu().model_copy(
        update={"model": "Ryzen 7 7800X", "architecture": "Zen 4"}
    )
    x3d = make_cpu().model_copy(
        update={"model": "Ryzen 7 7800X3D", "architecture": "Zen 4"}
    )
    assert cpu_gaming_index(x3d) > cpu_gaming_index(plain)


def test_newer_architecture_scores_higher():
    zen3 = make_cpu().model_copy(update={"architecture": "Zen 3"})
    zen4 = make_cpu().model_copy(update={"architecture": "Zen 4"})
    assert cpu_gaming_index(zen4) > cpu_gaming_index(zen3)


def test_extra_cores_matter_for_work_not_for_games():
    eight = make_cpu().model_copy(update={"cores": 8, "architecture": "Zen 4"})
    sixteen = make_cpu().model_copy(update={"cores": 16, "architecture": "Zen 4"})
    assert cpu_gaming_index(sixteen) == cpu_gaming_index(eight)
    # Вдвое больше ядер — почти вдвое выше оценка (точное «вдвое» мешает округление до десятых)
    assert cpu_multicore_index(sixteen) == pytest.approx(
        2 * cpu_multicore_index(eight), rel=0.01
    )


def test_gaming_score_is_bottleneck():
    gpu = FAST_GPU  # RTX 4080, индекс 72
    weak = make_cpu().model_copy(update={"architecture": "Zen 2", "cores": 4})
    strong = make_cpu().model_copy(
        update={"architecture": "Zen 5", "cores": 8, "boost_clock_mhz": 5500}
    )
    # Слабый процессор ограничивает: оценка ниже индекса видеокарты
    assert GAMING.score(weak, gpu) < gpu_index(gpu)
    # Сильный — видеокарта упирается в себя: оценка равна её индексу
    assert GAMING.score(strong, gpu) == gpu_index(gpu)


def test_faster_cpu_does_not_help_when_gpu_bound():
    gpu = SLOW_GPU  # RTX 4060
    fast = make_cpu().model_copy(update={"architecture": "Zen 4"})
    faster = make_cpu().model_copy(
        update={"architecture": "Zen 5", "model": "Ryzen 7 9800X3D"}
    )
    assert GAMING.score(fast, gpu) == GAMING.score(faster, gpu)


def test_cpu_feeds_gpu_is_configurable():
    gpu = FAST_GPU
    cpu = make_cpu().model_copy(update={"architecture": "Zen 3"})
    assert GamingProfile(cpu_feeds_gpu=0.5).score(cpu, gpu) < GAMING.score(cpu, gpu)


def test_workstation_prefers_cores():
    gpu = SLOW_GPU
    eight = make_cpu().model_copy(update={"cores": 8, "architecture": "Zen 4"})
    sixteen = make_cpu().model_copy(update={"cores": 16, "architecture": "Zen 4"})
    assert WORKSTATION.score(sixteen, gpu) > WORKSTATION.score(eight, gpu)


def test_big_budget_gets_fast_gpu():
    result = best_build(catalog(), Decimal(2000))
    assert result.solution.build.gpu.id == "gpu-fast"
    assert result.solution.total == Decimal(1620)  # 200 + 900 + 520


def test_smaller_budget_falls_back_to_slower_gpu():
    result = best_build(catalog(), Decimal(1100))
    assert result.solution.build.gpu.id == "gpu-slow"
    assert result.solution.total <= Decimal(1100)


def test_budget_too_small():
    assert best_build(catalog(), Decimal(500)) is None


def test_skips_pairs_over_budget_without_solving():
    result = best_build(catalog(), Decimal(1100))
    # Пара с RTX 4080 дороже бюджета уже по нижней границе — солвер для неё не запускался
    assert result.pairs_considered == 2
    assert result.pairs_solved == 1


def test_cheapest_per_key_keeps_first():
    parts = ["a1", "b1", "a2", "b2"]
    assert cheapest_per_key(parts, key=lambda p: p[0]) == ["a1", "b1"]


def test_result_is_compatible():
    result = best_build(catalog(), Decimal(2000))
    assert result.solution.issues == []
    assert isinstance(result.solution.build, Build)
