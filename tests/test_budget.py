from decimal import Decimal

from pcbuilder.domain.models import Build
from pcbuilder.recommender.budget import best_build, cheapest_per_key
from pcbuilder.recommender.scores import (
    Profile,
    cpu_performance,
    gpu_performance,
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


def test_gpu_performance_known_and_unknown():
    assert gpu_performance(FAST_GPU) > gpu_performance(SLOW_GPU)
    unknown = FAST_GPU.model_copy(update={"chipset": "GeForce GTX 460"})
    assert gpu_performance(unknown) == 0


def test_x3d_beats_same_cpu_without_cache():
    plain = make_cpu().model_copy(
        update={"model": "Ryzen 7 7800X", "architecture": "Zen 4"}
    )
    x3d = make_cpu().model_copy(
        update={"model": "Ryzen 7 7800X3D", "architecture": "Zen 4"}
    )
    assert cpu_performance(x3d) > cpu_performance(plain)


def test_newer_architecture_scores_higher():
    zen3 = make_cpu().model_copy(update={"architecture": "Zen 3"})
    zen4 = make_cpu().model_copy(update={"architecture": "Zen 4"})
    assert cpu_performance(zen4) > cpu_performance(zen3)


def test_profile_weights():
    gpu_heavy = Profile("test", gpu_weight=1.0, cpu_weight=0.0)
    assert gpu_heavy.score(CPU, FAST_GPU) == gpu_performance(FAST_GPU)


def test_big_budget_gets_fast_gpu():
    result = best_build(catalog(), Decimal(2000))
    assert result is not None
    assert result.solution.build.gpu is not None
    assert result.solution.build.gpu.id == "gpu-fast"
    assert result.solution.total == Decimal(1620)  # 200 + 900 + 520


def test_smaller_budget_falls_back_to_slower_gpu():
    result = best_build(catalog(), Decimal(1100))
    assert result is not None
    assert result.solution.build.gpu is not None
    assert result.solution.build.gpu.id == "gpu-slow"
    assert result.solution.total <= Decimal(1100)


def test_budget_too_small():
    assert best_build(catalog(), Decimal(500)) is None


def test_skips_pairs_over_budget_without_solving():
    result = best_build(catalog(), Decimal(1100))
    assert result is not None
    # Пара с RTX 4080 дороже бюджета уже по нижней границе — солвер для неё не запускался
    assert result.pairs_considered == 2
    assert result.pairs_solved == 1


def test_cheapest_per_key_keeps_first():
    parts = ["a1", "b1", "a2", "b2"]
    assert cheapest_per_key(parts, key=lambda p: p[0]) == ["a1", "b1"]


def test_result_is_compatible():
    result = best_build(catalog(), Decimal(2000))
    assert result is not None
    assert result.solution.issues == []
    assert isinstance(result.solution.build, Build)
