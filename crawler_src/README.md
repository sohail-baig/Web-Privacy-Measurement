# Online Tracking & Privacy - Assignment 2

Run all commands from the project root (the folder containing `report.ipynb`).

## Crawl

```powershell
python crawler_src/crawl.py -m desktop -l crawler_src/sites.csv
python crawler_src/crawl.py -m mobile -l crawler_src/sites.csv
python crawler_src/crawl.py -m block -l crawler_src/sites.csv
python crawler_src/crawl.py -m ignore -l crawler_src/sites.csv
```

The list contains 30 universities: ten each from NL, UK and US. Each visit uses a fresh Chromium context, `en-GB` locale and `Europe/Amsterdam` timezone. Desktop uses 1366 x 768; Mobile requires the actual Pixel 10 preset. Block filters Advertising, Analytics, Social, FingerprintingInvasive and FingerprintingGeneral using frozen Disconnect lists. Service workers are blocked and routing is installed in every mode.

Sequence: load (60-second timeout), wait 10 seconds, pre-consent screenshot, accept consent, wait 5 seconds, post-consent screenshot, bounded scrolling, wait 5 seconds, close. Ignore skips consent, its wait and the post-consent screenshot. The handler checks English/Dutch controls in frames and open shadow roots and verifies dismissal. Review `not_found` screenshots manually; unfamiliar banners can be missed.

Results are saved as `<site>.har`, `<site>_pre_consent.png`, `<site>_post_consent.png` and `<site>.webm` in `crawl_data_<mode>/`. Ignore has no post-consent screenshot. `manifest.json` records outcomes and enables resume. Repeat the same command to retry failed visits and skip completed ones. Changed code/settings/reference inputs require a separate run with `--output-root measurements/run-02`; preserve original evidence.

## Analyse and read the report

```powershell
python -m analysis.run --prepare
python -m analysis.run --question 1 2 3 4 5 6 7 8 9 10 11 12
```

Preparation requires the original crawl artifacts and manifests. Results are generated in `analysis/output/`. Analysis counts received HTTP responses, keeps completed visits with zero requests, and measures third-partyness against the final page domain. Shared Disconnect and Public Suffix List snapshots are in `crawler_src/reference_data/`; Q8 uses `tranco.csv` there. Q12 saves timestamped DNS results in `analysis/output/dns_cache.json`. Preserve the original cache to reproduce the report instead of querying current DNS.

Open `report.ipynb` in a notebook viewer to read its saved text, figures and tables without execution. To rerun it, open it from this project root after restoring the original analysis outputs. Set `RECOMPUTE = True` only with the original prepared CSVs and DNS cache. A Jupyter-capable editor is optional; crawler and analysis commands need only `requirements.txt`.

## Submission contents and remaining data

Submit `report.ipynb`, `crawler_src/`, `analysis/`, the four `crawl_data_<mode>/` folders and `requirements.txt`. Keep only Python source in `analysis/` for the requested layout; generated outputs are working files. Keep crawl manifests alongside the artifacts so preparation can reproduce the datasets. Exclude `.git/`, `.venv/`, `__pycache__/`, `.staging/`, notebook checkpoints and `.gitkeep` placeholders from the upload.

**This checkout does not contain crawl artifacts or the original DNS cache.** Git excludes these files. Restore them from the measurement machine before submission. The saved report describes 119 completed visits (30 Desktop, 29 Mobile, 30 Block, 30 Ignore); check its missing Mobile visit and limitations against the original evidence. Cleaning the source tree does not verify those results.

The two `__init__.py` files mark `crawler_src` and `analysis` as Python packages. Keep them for predictable imports and `python -m analysis.run`.
