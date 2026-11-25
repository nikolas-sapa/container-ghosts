import math

import numpy as np
from scipy.stats import beta, norm


def _binom_tail(k: int, n: int) -> float:
    return sum(math.comb(n, j) for j in range(k, n + 1)) / 2**n


def exact_mcnemar(n10: int, n01: int, alternative: str = "greater") -> float:
    n = n10 + n01
    if n == 0:
        return 1.0
    if alternative == "greater":
        return min(1.0, _binom_tail(n10, n))
    if alternative == "less":
        return min(1.0, sum(math.comb(n, j) for j in range(0, n10 + 1)) / 2**n)
    if alternative != "two-sided":
        raise ValueError("alternative must be greater, less, or two-sided")
    observed = math.comb(n, n10) / 2**n
    total = 0.0
    for j in range(n + 1):
        prob = math.comb(n, j) / 2**n
        if prob <= observed + 1e-15:
            total += prob
    return min(1.0, total)


def discordance(cross_flips, repeat_flips) -> dict:
    cross = np.asarray(cross_flips, dtype=bool)
    repeat = np.asarray(repeat_flips, dtype=bool)
    if cross.shape != repeat.shape:
        raise ValueError("cross and repeat indicators must have identical shape")
    n10 = int(np.sum(cross & ~repeat))
    n01 = int(np.sum(~cross & repeat))
    n11 = int(np.sum(cross & repeat))
    n00 = int(np.sum(~cross & ~repeat))
    n = int(cross.size)
    return {
        "n": n,
        "n10": n10,
        "n01": n01,
        "n11": n11,
        "n00": n00,
        "delta": (n10 - n01) / n if n else float("nan"),
        "mcnemar_one_sided_p": exact_mcnemar(n10, n01, "greater"),
    }


def clopper_pearson(x: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    if not 0 <= x <= n:
        raise ValueError("require 0 <= x <= n")
    alpha = 1.0 - confidence
    lower = 0.0 if x == 0 else float(beta.ppf(alpha / 2, x, n - x + 1))
    upper = 1.0 if x == n else float(beta.ppf(1 - alpha / 2, x + 1, n - x))
    return lower, upper


def newcombe_wilson(x: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    if n <= 0:
        raise ValueError("n must be positive")
    alpha = 1.0 - confidence
    z = float(norm.ppf(1 - alpha / 2))
    phat = x / n
    denom = 1 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    half = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / denom
    return max(0.0, center - half), min(1.0, center + half)


def paired_bootstrap_ci(values, confidence: float = 0.95, iterations: int = 10000, seed: int = 448448) -> tuple[float, float]:
    arr = np.asarray(values, dtype=float)
    if arr.ndim != 1 or arr.size == 0:
        raise ValueError("values must be a nonempty one-dimensional array")
    rng = np.random.default_rng(seed)
    means = np.empty(iterations)
    for i in range(iterations):
        means[i] = arr[rng.integers(0, arr.size, arr.size)].mean()
    alpha = 1.0 - confidence
    return float(np.quantile(means, alpha / 2)), float(np.quantile(means, 1 - alpha / 2))


def holm_adjust(pvalues) -> list[float]:
    p = np.asarray(pvalues, dtype=float)
    order = np.argsort(p)
    adjusted = np.empty_like(p)
    running = 0.0
    m = len(p)
    for rank, idx in enumerate(order):
        value = min(1.0, (m - rank) * p[idx])
        running = max(running, value)
        adjusted[idx] = running
    return adjusted.tolist()


def exact_repeat_noise_comparison(cross_flips, repeat_flips, confidence: float = 0.95) -> dict:
    table = discordance(cross_flips, repeat_flips)
    repeat_rate = float(np.mean(np.asarray(repeat_flips, dtype=bool))) if table["n"] else float("nan")
    table.update({
        "exact_repeat_rate": repeat_rate,
        "exact_repeat_rate_clopper_pearson": clopper_pearson(
            int(np.sum(np.asarray(repeat_flips, dtype=bool))), table["n"], confidence
        ) if table["n"] else (float("nan"), float("nan")),
    })
    return table
