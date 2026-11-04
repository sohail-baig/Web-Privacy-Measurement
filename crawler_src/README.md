# Crawler

From the project/ZIP root, create a Python 3.12 virtual environment, install `requirements.txt`, then run `python -m playwright install chromium`. The full setup and measurement notes are in the root README.

```text
python crawler_src/crawl.py -m ignore -l sites.csv
python crawler_src/crawl.py -m desktop -l sites.csv
python crawler_src/crawl.py -m mobile -l sites.csv
python crawler_src/crawl.py -m block -l sites.csv
```

Add `--output-root PATH` to isolate a run. Modes run sequentially, one fresh context per site. Do not run two processes into the same root.

`consent.py` is deliberately unfinished. Until its handler is implemented and `IMPLEMENTED=True`, the three accept-consent modes fail before visiting sites. Tests inject a fixture handler; the CLI cannot bypass this gate. A `not_found` result means the implemented detector found no dialog; verify these visits manually.

Normal sequence: load → 10s → pre screenshot → accept → 5s → post screenshot → stepped scroll → 5s → close. Ignore skips accept, the associated 5s wait and the second screenshot. Scrolling stops at the bottom, after three unchanged positions, or at a 30s cap. Consent dialogs are never dismissed to enable Ignore scrolling.

The five blocking categories are Advertising, Analytics, Social, FingerprintingInvasive and FingerprintingGeneral. Routing is installed in every mode; service workers are disabled in every mode. HAR content is embedded and full metadata retained. Video size follows the viewport. Timestamps are UTC; browser timezone is Europe/Amsterdam.

`manifest.json` records visits and attempts. Completed files are checksum-validated before skipping them. `.staging/` retains failure diagnostics and blocked-URL evidence; blocked requests never enter received-response analyses. Failed/interrupted visits retry on the next invocation. If fingerprints differ, start a new output root. Do not edit manifests to bypass this protection.

Exit codes: 0 complete; 1 visit failures/pending work; 2 preflight/configuration error; 130 user interruption.
