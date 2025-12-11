# Copilot instructions for pandemic_programming

Purpose
- Brief: help AI coding agents become productive quickly in this replication package.

**Big picture**
- **Repo type:** replication package for an R-based analysis with some Python helper scripts.
- **Major components:** [Rmd/Analysis for PP.Rmd](Rmd/Analysis%20for%20PP.Rmd) (main runnable document), [analysis/SEM.R](analysis/SEM.R) (confirmatory/SEM code), [analysis/BDAMLMs.R](analysis/BDAMLMs.R) (Bayesian analyses), [covid-19-recoding/](covid-19-recoding/) (recode + histogram generation), and [data/](data/) (CSV/Excel inputs).

**How to run & developer workflows**
- R-driven analysis: open [pandemic_programming.Rproj](pandemic_programming.Rproj) in RStudio and knit [Rmd/Analysis for PP.Rmd](Rmd/Analysis%20for%20PP.Rmd). The `Rproj` file sets the working directory to the repo root.
- Key R scripts can be run interactively in RStudio; use [analysis/SEM.R](analysis/SEM.R) for the main SEM flow.
- Python helper: run [analyze_second_round.py](analyze_second_round.py) from the repo root. Example invocations (from script docstring):

```bash
python3 analyze_second_round.py
python3 analyze_second_round.py --describe
python3 analyze_second_round.py --output-csv data/covid_data_2nd_round.csv
```

**Project-specific data & patterns**
- Column mapping: [data/Column mapping.txt](data/Column%20mapping.txt) is a text file with lines like `'Thai question text':'ShortName',`. The Python helper reads it by wrapping in `{ ... }` and using `ast.literal_eval` (see `load_column_mapping` in [analyze_second_round.py](analyze_second_round.py)).
- Non-ASCII filenames: the second-round Excel file name contains Thai characters. Use `Path`-based APIs and explicit UTF-8 reads; the Python script already expects UTF-8.
- Plot outputs for the Python helper are saved under `analysis/second_round_plots` by default; R outputs (knit HTML) are in `docs/`.

**Dependencies & environments**
- R packages: assume standard tidyverse/SEM packages are required by the Rmd and `analysis/*.R` files; run the Rmd in RStudio which will prompt for missing packages.
- Python: `pandas`, `matplotlib`. The repo contains a `pyenv` usage in local workflow; if you use a virtualenv, name is not required but the script is lightweight.

**Conventions & code patterns**
- The R workflow treats the R project root as the canonical working directory. Avoid changing working directories inside scripts.
- Re-usable recoding logic lives in `covid-19-recoding/` — prefer reusing its routines when adjusting variable transformations.
- When renaming columns for analyses, the mapping file is authoritative; maintain it when creating derived CSVs.

**Editing guidance for AI agents**
- Small, focused edits: update `analysis/SEM.R` or `Rmd/` only if changes are consistent with the Rmd narrative. Prefer adding small helper R scripts to `covid-19-recoding/` for new recoding steps.
- For Python: maintain UTF-8-safe I/O and use `Path` objects as in `analyze_second_round.py`.
- Tests: there are no unit tests in the repo; validate changes by kniting the Rmd or running the Python script with `--describe`.

If any section is unclear or you want more details (exact package lists, examples of recoding logic), tell me which area to expand.
