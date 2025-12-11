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
import json
import math
from pathlib import Path
from typing import Iterable, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


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
    parser.add_argument(
        "--export-json",
        type=str,
        default=None,
        help="Optional path to write per-respondent values and stats as JSON (for the report UI).",
    )
    parser.add_argument(
        "--boxplot-path",
        type=str,
        default=None,
        help="Optional path to save a WHO before/after boxplot grouped by age (PNG).",
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


def _normal_sf(z: float) -> float:
    """Survival function of standard normal using math.erfc (no SciPy dependency)."""
    return 0.5 * math.erfc(z / math.sqrt(2))


def wilcoxon_signed_rank(diff: np.ndarray) -> Tuple[float, float]:
    """
    Wilcoxon signed-rank test (two-sided).
    Uses scipy if available; otherwise falls back to a normal approximation.
    Returns (statistic, pvalue).
    """
    try:
        from scipy import stats  # type: ignore
    except Exception:
        stats = None

    nz = diff[diff != 0]
    if nz.size == 0:
        return math.nan, math.nan

    if stats is not None:
        res = stats.wilcoxon(
            nz, zero_method="wilcox", alternative="two-sided", correction=False, method="auto"
        )
        return float(res.statistic), float(res.pvalue)

    # Fallback: normal approximation with average ranks (no tie correction here).
    abs_vals = np.abs(nz)
    ranks = pd.Series(abs_vals).rank(method="average").to_numpy()
    pos_mask = nz > 0
    w_pos = float(ranks[pos_mask].sum())
    w_neg = float(ranks[~pos_mask].sum())
    w_stat = min(w_pos, w_neg)

    n = len(ranks)
    mean_w = n * (n + 1) / 4
    var_w = n * (n + 1) * (2 * n + 1) / 24
    z = (w_stat - mean_w) / math.sqrt(var_w) if var_w > 0 else math.nan
    p_val = 2 * _normal_sf(abs(z)) if not math.isnan(z) else math.nan
    return w_stat, p_val


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


def _clean_value(v):
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


def to_json_text(obj) -> str:
    """Recursively convert NaN/inf to None and dump as JSON text."""
    def clean(o):
        if isinstance(o, dict):
            return {k: clean(v) for k, v in o.items()}
        if isinstance(o, list):
            return [clean(v) for v in o]
        return _clean_value(o)

    return json.dumps(clean(obj), ensure_ascii=False, indent=2)


def save_who_boxplot(qa_df: pd.DataFrame, output_path: Path) -> None:
    """Save WHO before/after boxplot grouped by age."""
    subset = qa_df[["Age", "WHO_Before", "WHO_After"]].dropna()
    if subset.empty:
        print("No data available for WHO boxplot.")
        return

    ages = sorted(subset["Age"].unique())
    before_data = [subset.loc[subset["Age"] == age, "WHO_Before"].astype(float) for age in ages]
    after_data = [subset.loc[subset["Age"] == age, "WHO_After"].astype(float) for age in ages]

    fig, ax = plt.subplots(figsize=(9, 5.5))
    gap = 0.35
    positions_before = [i * 2 for i in range(len(ages))]
    positions_after = [p + gap for p in positions_before]

    boxprops_before = dict(facecolor="#4fd1c5", alpha=0.45, color="#4fd1c5")
    boxprops_after = dict(facecolor="#f59e0b", alpha=0.45, color="#f59e0b")

    ax.boxplot(before_data, positions=positions_before, widths=0.3, patch_artist=True, boxprops=boxprops_before,
               medianprops=dict(color="#0e1117"), whiskerprops=dict(color="#4fd1c5"), capprops=dict(color="#4fd1c5"))
    ax.boxplot(after_data, positions=positions_after, widths=0.3, patch_artist=True, boxprops=boxprops_after,
               medianprops=dict(color="#0e1117"), whiskerprops=dict(color="#f59e0b"), capprops=dict(color="#f59e0b"))

    ax.set_xticks([(b + a) / 2 for b, a in zip(positions_before, positions_after)])
    ax.set_xticklabels([str(int(age)) for age in ages])
    ax.set_xlabel("Age")
    ax.set_ylabel("WHO score")
    ax.set_title("WHO Before vs After by Age (QA role)")

    # Custom legend
    handles = [
        plt.Line2D([0], [0], color="#4fd1c5", lw=4, label="WHO_Before"),
        plt.Line2D([0], [0], color="#f59e0b", lw=4, label="WHO_After"),
    ]
    ax.legend(handles=handles, frameon=False)
    ax.grid(True, axis="y", linestyle="--", alpha=0.25)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    print(f"Saved WHO boxplot to {output_path}")


def main() -> None:
    args = parse_args()
    df = load_data(Path(args.file))

    cols = ["RolesIncludeDeveloper", "HPQ_Before", "HPQ_After", "Age", "WHO_Before", "WHO_After"]
    missing_cols = [c for c in cols if c not in df.columns]
    if missing_cols:
        raise KeyError(f"Missing required columns: {missing_cols}")

    qa = df.loc[df["RolesIncludeDeveloper"] == args.role, ["ID", "Age", "HPQ_Before", "HPQ_After", "WHO_Before", "WHO_After"]]
    qa = qa.dropna(subset=["HPQ_Before", "HPQ_After"])
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

    if args.export_json:
        out_path = Path(args.export_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "role": args.role,
            "n": int(len(diff)),
            "exclude_negative_after": bool(args.exclude_negative_after),
            "stats": {"before": b_desc, "after": a_desc, "diff": d_desc},
            "tests": {
                "sign": {"n_pos": n_pos, "n_neg": n_neg, "n_nonzero": n_nonzero, "p": p_sign},
                "paired_t": {"t": t_stat, "p": p_t},
                "wilcoxon": {"w": w_stat, "p": w_p},
            },
            "bootstrap_ci": {"mean_diff": {"lower": ci_lo, "upper": ci_hi}, "samples": args.bootstrap_samples},
            "data": [
                {
                    "id": int(row["ID"]) if not pd.isna(row.get("ID", np.nan)) else int(idx),
                    "before": float(row["HPQ_Before"]),
                    "after": float(row["HPQ_After"]),
                    "diff": float(row["HPQ_After"] - row["HPQ_Before"]),
                }
                for idx, row in qa.iterrows()
            ],
            "source_file": str(args.file),
        }
        out_path.write_text(to_json_text(payload), encoding="utf-8")
        print(f"Wrote JSON report payload to {out_path}")

    if args.boxplot_path:
        save_who_boxplot(qa, Path(args.boxplot_path))


if __name__ == "__main__":
    main()
