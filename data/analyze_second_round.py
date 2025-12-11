#!/usr/bin/env python3
"""
Quick analysis script for the second-round COVID-19 developer survey.

It reads the Excel file
`data/แบบสอบถามเรื่องผลกระทบจาก COVID-19 กับนักพัฒนาซอฟต์แวร์_shortened (Responses)-2nd_round.xlsx`,
optionally renames columns using `data/Column mapping.txt`, prints a basic
summary to the console, and can export a cleaned CSV.

Usage examples (run from the repository root):

    python3 analyze_second_round.py
    python3 analyze_second_round.py --describe
    python3 analyze_second_round.py --output-csv data/covid_data_2nd_round.csv

This script assumes `pandas` is installed.
"""

from __future__ import annotations

import argparse
import ast
from pathlib import Path
from typing import Dict, Optional

import matplotlib.pyplot as plt
import pandas as pd
from pandas.api.types import is_numeric_dtype


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT_XLSX = PROJECT_ROOT / (
    "data/แบบสอบถามเรื่องผลกระทบจาก COVID-19 "
    "กับนักพัฒนาซอฟต์แวร์_shortened (Responses)-2nd_round.xlsx"
)
DEFAULT_MAPPING_TXT = PROJECT_ROOT / "data" / "Column mapping.txt"
DEFAULT_PLOTS_DIR = PROJECT_ROOT / "analysis" / "second_round_plots"


def load_column_mapping(path: Path) -> Dict[str, str]:
    """
    Load the Thai → short-name column mapping from a text file.

    The file `Column mapping.txt` contains lines like:

        'Thai question text':'ShortName',

    This function wraps the contents in braces and uses `ast.literal_eval`
    so we do not have to re-encode the mapping here.
    """
    text = path.read_text(encoding="utf-8")
    mapping = ast.literal_eval("{" + text + "}")
    # Ensure keys are plain strings without surrounding whitespace
    return {str(k).strip(): str(v).strip() for k, v in mapping.items()}


def load_survey(
    input_path: Path,
    mapping_path: Optional[Path] = None,
) -> pd.DataFrame:
    """
    Load the Excel survey file and optionally rename columns.
    """
    df = pd.read_excel(input_path)

    if mapping_path is not None and mapping_path.exists():
        mapping = load_column_mapping(mapping_path)
        rename_map: Dict[str, str] = {}
        for col in df.columns:
            key = str(col).strip()
            if key in mapping:
                rename_map[col] = mapping[key]
        if rename_map:
            df = df.rename(columns=rename_map)

    return df


def basic_summary(df: pd.DataFrame) -> None:
    """
    Print a compact overview of the dataset.
    """
    print(f"Rows: {df.shape[0]}, columns: {df.shape[1]}")

    print("\nColumn types:")
    print(df.dtypes)

    print("\nMissing values (top 20 columns):")
    missing = df.isna().sum().sort_values(ascending=False)
    print(missing.head(20))

    # Some key variables (printed only if present)
    interesting_cols = [
        "Gender",
        "Age",
        "RolesIncludeDeveloper",
        "YearsOfExperience",
        "YearsOfWorkFromHomeExperience",
        "Education",
        "OrganizationSize",
        "COVIDStatus",
        "Isolation",
    ]

    for col in interesting_cols:
        if col in df.columns:
            print(f"\nValue counts for {col}:")
            print(df[col].value_counts(dropna=False))


def _sanitize_filename(name: str) -> str:
    safe = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name)
    return safe or "column"


def visualize_columns(
    df: pd.DataFrame,
    output_dir: Path,
    max_categories: int = 25,
) -> None:
    """
    Save simple visualizations for all columns as PNG files.

    - Numeric columns: histogram.
    - Non-numeric columns: bar plot of the top `max_categories` categories.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n=== SAVING COLUMN PLOTS TO {output_dir} ===")

    for idx, col in enumerate(df.columns):
        series = df[col]
        col_name = str(col)
        safe_name = _sanitize_filename(col_name)
        plot_path = output_dir / f"{idx:03d}_{safe_name}.png"

        plt.figure(figsize=(6, 4))

        if is_numeric_dtype(series):
            numeric = pd.to_numeric(series, errors="coerce").dropna()
            if numeric.empty:
                plt.text(0.5, 0.5, "No numeric data", ha="center", va="center")
                plt.axis("off")
            else:
                plt.hist(numeric, bins=20, edgecolor="black")
                plt.xlabel(col_name)
                plt.ylabel("Count")
                plt.title(col_name)
        else:
            counts = series.value_counts(dropna=False)
            if counts.empty:
                plt.text(0.5, 0.5, "No data", ha="center", va="center")
                plt.axis("off")
            else:
                counts = counts.head(max_categories)
                counts.plot(kind="bar")
                plt.ylabel("Count")
                plt.title(col_name)
                plt.xticks(rotation=45, ha="right")

        plt.tight_layout()
        plt.savefig(plot_path, dpi=150)
        plt.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Analyze the second-round COVID-19 developer survey Excel file "
            "and optionally export a CSV."
        )
    )
    parser.add_argument(
        "--input",
        type=str,
        default=None,
        help=(
            "Path to the Excel file. "
            "Defaults to the standard second-round survey in ./data/."
        ),
    )
    parser.add_argument(
        "--mapping",
        type=str,
        default=None,
        help=(
            "Path to Column mapping.txt. "
            "If omitted, the default ./data/Column mapping.txt is used "
            "when it exists."
        ),
    )
    parser.add_argument(
        "--output-csv",
        type=str,
        default=None,
        help="Optional path to write a cleaned CSV version of the data.",
    )
    parser.add_argument(
        "--describe",
        action="store_true",
        help="Print a full pandas describe(include='all') summary.",
    )
    parser.add_argument(
        "--plots-dir",
        type=str,
        default=None,
        help=(
            "Directory to save per-column plots as PNG files. "
            "If omitted, no plots are generated."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    input_path = Path(args.input) if args.input else DEFAULT_INPUT_XLSX
    mapping_path: Optional[Path]

    if args.mapping:
        mapping_path = Path(args.mapping)
    else:
        mapping_path = DEFAULT_MAPPING_TXT if DEFAULT_MAPPING_TXT.exists() else None

    if not input_path.exists():
        raise SystemExit(f"Input Excel file not found: {input_path}")

    if mapping_path is None:
        print("No column-mapping file provided or found; keeping original column names.")
    else:
        print(f"Using column-mapping file: {mapping_path}")

    print(f"Loading survey data from: {input_path}")
    df = load_survey(input_path, mapping_path)

    print("\n=== BASIC SUMMARY ===")
    basic_summary(df)

    if args.describe:
        print("\n=== FULL DESCRIBE (include='all') ===")
        with pd.option_context("display.max_rows", 200, "display.max_columns", 200):
            print(df.describe(include="all").transpose())

    if args.plots_dir:
        plots_dir = Path(args.plots_dir)
        visualize_columns(df, plots_dir)
        print(f"\nSaved per-column plots under: {plots_dir}")

    if args.output_csv:
        output_path = Path(args.output_csv)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
        print(f"\nWrote cleaned CSV to: {output_path}")


if __name__ == "__main__":
    main()
