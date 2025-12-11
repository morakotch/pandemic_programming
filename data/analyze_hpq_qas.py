"""
Analyze HPQ before vs after for QA respondents.

Usage:
    python data/analyze_hpq_qas.py \
        --file "data/covid_data_12June2023_after_remove_consent for chatgpt.xlsx" \
        --role "Quality Assurance Specialist, Software Testers"

Options:
    --exclude-negative-after   Drop rows where HPQ_After < 0 (helps handle obvious outliers).
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Iterable, Tuple

import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HPQ before/after comparison for QA role.")
    parser.add_argument(
        "--file",
        default="data/covid_data_12June2023_after_remove_consent for chatgpt.xlsx",
        help="Input Excel/CSV file (default: cleaned June 12 data).",
    )
    parser.add_argument(
        "--role",
        default="Quality Assurance Specialist, Software Testers",
        help="Exact role label to filter on.",
    )
    parser.add_argument(
        "--exclude-negative-after",
        action="store_true",
        help="Exclude rows with HPQ_After < 0 (optional outlier handling).",
    )
    parser.add_argument(
        "--bootstrap-samples",
        type=int,
        default=20000,
        help="Number of bootstrap draws for the mean difference CI.",
    )
    return parser.parse_args()


def load_data(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")
    if path.suffix.lower() in {".xls", ".xlsx"}:
        return pd.read_excel(path)
    return pd.read_csv(path)


def sign_test(diff: np.ndarray) -> Tuple[int, int, int, float]:
    """Exact two-sided binomial sign test; returns n_pos, n_neg, n_nonzero, p."""
    n_pos = int((diff > 0).sum())
    n_neg = int((diff < 0).sum())
    n_nonzero = n_pos + n_neg
    if n_nonzero == 0:
        return n_pos, n_neg, n_nonzero, math.nan
    k = min(n_pos, n_neg)
    p = 0.5
    # exact CDF using comb; OK for small n (n=15 here).
    cdf = sum(math.comb(n_nonzero, i) * (p**i) * ((1 - p) ** (n_nonzero - i)) for i in range(k + 1))
    p_two = min(1.0, 2 * cdf)
    return n_pos, n_neg, n_nonzero, p_two


def paired_t(diff: np.ndarray) -> Tuple[float, float, float]:
    """Return mean_diff, sd_diff, t_stat. p-value computed only if scipy is available."""
    mean_diff = float(diff.mean())
    sd_diff = float(diff.std(ddof=1))
    n = len(diff)
    t_stat = mean_diff / (sd_diff / math.sqrt(n)) if n > 1 and sd_diff > 0 else math.nan
    return mean_diff, sd_diff, t_stat


def paired_t_pvalue(t_stat: float, n: int) -> float:
    """Two-sided p-value for t statistic using scipy if present; else NaN."""
    try:
        from scipy import stats  # type: ignore
    except Exception:
        return math.nan
    return float(2 * stats.t.sf(abs(t_stat), df=n - 1))


def bootstrap_mean_ci(diff: np.ndarray, samples: int = 20000, seed: int = 42) -> Tuple[float, float]:
    rng = np.random.default_rng(seed)
    n = len(diff)
    idx = rng.integers(0, n, size=(samples, n))
    boot_means = diff[idx].mean(axis=1)
    lo, hi = np.quantile(boot_means, [0.025, 0.975])
    return float(lo), float(hi)


def wilcoxon_signed_rank(diff: np.ndarray) -> Tuple[float, float]:
    """
    Wilcoxon signed-rank test (two-sided) using scipy if available; otherwise returns (nan, nan).
    Returns (statistic, pvalue).
    """
    try:
        from scipy import stats  # type: ignore
    except Exception:
        return math.nan, math.nan
    res = stats.wilcoxon(diff, zero_method="wilcox", alternative="two-sided", correction=False)
    return float(res.statistic), float(res.pvalue)


def describe(arr: Iterable[float]) -> dict:
    a = np.asarray(list(arr), dtype=float)
    return {
        "n": int(a.size),
        "mean": float(a.mean()),
        "sd": float(a.std(ddof=1)),
        "median": float(np.median(a)),
        "min": float(a.min()),
        "max": float(a.max()),
    }


def main() -> None:
    args = parse_args()
    df = load_data(Path(args.file))

    cols = ["RolesIncludeDeveloper", "HPQ_Before", "HPQ_After"]
    missing_cols = [c for c in cols if c not in df.columns]
    if missing_cols:
        raise KeyError(f"Missing required columns: {missing_cols}")

    qa = df.loc[df["RolesIncludeDeveloper"] == args.role, ["HPQ_Before", "HPQ_After"]].dropna()
    if args.exclude_negative_after:
        qa = qa.loc[qa["HPQ_After"] >= 0]

    if qa.empty:
        print("No QA rows with non-missing HPQ_Before/HPQ_After after filtering.")
        return

    before = qa["HPQ_Before"].to_numpy(dtype=float)
    after = qa["HPQ_After"].to_numpy(dtype=float)
    diff = after - before

    print(f"QA rows analyzed: {len(diff)} (role match: {args.role})")
    b_desc = describe(before)
    a_desc = describe(after)
    d_desc = describe(diff)
    print(f"HPQ_Before: mean={b_desc['mean']:.3f}, sd={b_desc['sd']:.3f}, "
          f"median={b_desc['median']:.3f}, min={b_desc['min']}, max={b_desc['max']}")
    print(f"HPQ_After : mean={a_desc['mean']:.3f}, sd={a_desc['sd']:.3f}, "
          f"median={a_desc['median']:.3f}, min={a_desc['min']}, max={a_desc['max']}")
    print(f"Diff (After-Before): mean={d_desc['mean']:.3f}, sd={d_desc['sd']:.3f}, "
          f"median={d_desc['median']:.3f}, min={d_desc['min']:.3f}, max={d_desc['max']:.3f}")

    n_pos, n_neg, n_nonzero, p_sign = sign_test(diff)
    print(f"Sign test: n_pos={n_pos}, n_neg={n_neg}, n_nonzero={n_nonzero}, two-sided p~={p_sign:.4f}")

    mean_diff, sd_diff, t_stat = paired_t(diff)
    p_t = paired_t_pvalue(t_stat, len(diff))
    print(f"Paired t-test: mean diff={mean_diff:.3f}, sd diff={sd_diff:.3f}, t={t_stat:.3f}, p={p_t:.4f}")

    ci_lo, ci_hi = bootstrap_mean_ci(diff, samples=args.bootstrap_samples)
    print(f"Bootstrap 95% CI for mean diff: ({ci_lo:.3f}, {ci_hi:.3f}) using {args.bootstrap_samples} samples")

    w_stat, w_p = wilcoxon_signed_rank(diff)
    print(f"Wilcoxon signed-rank (two-sided): W={w_stat:.3f}, p={w_p:.4f}")


if __name__ == "__main__":
    main()
