# Online Tracking & Privacy — Assignment 2

Runnable foundation for NWI-IMC074. **This is not a completed assignment.** Ignore crawling, evidence capture, resume, data preparation, PDF rendering and packaging infrastructure work. Consent handling is implemented and validated on Desktop and Mobile; Q1–Q12 remain student tasks. The PDF is a visibly marked draft.

## Setup (Windows PowerShell, Python 3.12)

Open this folder in a terminal. Install Python 3.12 if `py -3.12` is unavailable.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

Use `.\.venv\Scripts\python.exe` in place of `python` below; activation is optional. All commands run from this project root. Dependencies are pinned, including transitive packages. Chromium is the revision installed by the pinned Playwright package.

## What you can run now

```powershell
python -m unittest discover -s tests -v
$env:OTP_BROWSER_TESTS='1'
python -m unittest discover -s tests -v
Remove-Item Env:OTP_BROWSER_TESTS
python -m analysis.run --prepare
python -m report.render
python submission.py
```

The browser tests use only a local HTTP server, synthetic data and temporary output. Normal tests skip browser tests unless explicitly enabled. They never crawl university websites. Data preparation succeeds before collection and writes empty, header-bearing tables plus coverage. The submission checker correctly exits nonzero while work is unfinished.

To collect real data, run one command at a time:

```powershell
python crawler_src/crawl.py -m ignore -l sites.csv
python crawler_src/crawl.py -m desktop -l sites.csv
python crawler_src/crawl.py -m mobile -l sites.csv
python crawler_src/crawl.py -m block -l sites.csv
```

**Desktop and Mobile are ready to run.** The generic consent handler prefers explicit accept-all controls (including a tiered prompt's "Complete" level), then consent-scoped English/Dutch acceptance labels and recognized CMP controls. It searches on-screen banners/dialogs, frames and open shadow roots, and verifies dismissal. `accepted` means an acceptance control was clicked, its banner or control disappeared and no active prompt remains; `not_found` means no supported banner was detected, not proof that consent was unnecessary. Unknown detected dialogs, disabled controls and clicks without dismissal return `failed`, retaining diagnostic evidence and leaving the visit retryable.

Start Desktop with `python crawler_src/crawl.py -m desktop -l sites.csv` (Mobile: `-m mobile`). Repeat the same command to resume. Review screenshots for `not_found` and failed visits. Preference-only flows, closed shadow roots and unfamiliar labels may need generic selector/keyword extensions; no site-specific code or external consent APIs are used. The shared handler is also used by Mobile and Block.

The required Pixel 10 descriptor is present in Playwright 1.64.1. An installation without it fails clearly. Desktop modes use 1366×768; mobile uses the full descriptor. All modes use `en-GB`, `Europe/Amsterdam`, blocked service workers and request routing. Routing disables browser HTTP caching consistently across modes. Record these measurement choices as limitations in the report.

## Resume and output

Repeat exactly the same command to resume. A complete visit is skipped only after its required evidence passes checksum validation. Navigation timeout is 60 seconds. Failed visits are retried on the next invocation; the crawler continues to the next site after an ordinary visit failure. Ctrl+C saves interruption state where possible. A hard kill leaves the current attempt pending for retry.

Each mode folder contains the assignment's flat filenames and `manifest.json`. Attempts and failure diagnostics live under `.staging/`; they are excluded from the submission ZIP. HARs and videos are finalized before completion is recorded. Original input domains determine filenames even after redirects. Metadata retains the final URL, country, outcome, timestamps and checksums.

Changing the site list, source code, browser/package version, settings or reference snapshots prevents reuse of incompatible state. Use a new location instead of deleting evidence:

```powershell
python crawler_src/crawl.py -m ignore -l sites.csv --output-root measurements/run-02
python -m analysis.run --prepare --root measurements/run-02
```

Only run one crawler process against an output root at a time. Preserve the same network location and measurement settings across the four modes. No live crawl data is shipped with this foundation.

## Reference data

`sites.csv` is the instructor's linked selection, unchanged: 30 universities, 10 per country. Input accepts a header and an optional university column, or headerless `domain,country` rows. Domains must be bare hostnames; invalid/duplicate entries fail before collection. Smaller lists are allowed for debugging; submission requires 30 sites covering NL/UK/US.

`crawler_src/reference_data/sources.json` records URLs, revisions, SHA-256 checksums and retrieval times. The frozen Disconnect services revision is `a277cd6`; entities revision is `cb1b0c1`. Classification supports multiple categories/entities and the `session-replay` metadata field. Hostname matches respect dot boundaries. Blocking uses precisely the five specified categories; CNAME analysis must later consider all categories.

The Public Suffix List is loaded from the local checked snapshot, including its private section. Automatic downloads and built-in snapshot fallbacks are disabled. Crawling/analysis code makes no external API calls. Website traffic is the measurement itself; Q12's future implementation will use DNS queries. Disconnect data retains its included attribution/noncommercial/share-alike license; the PSL license is included in its file header.

## Finish the assignment

1. Review consent outcomes in the saved evidence; extend generic selectors/labels if a banner is unsupported.
2. Collect and inspect all four modes. Check screenshots and videos, especially `not_found` consent outcomes.
3. Run preparation, implement Q1–Q12 in `analysis/questions.py`, and run each question. See `analysis/README.md` for dataset contracts.
4. Populate the report template with actual plots/tables, self-explanatory captions and Q13 reflections. Remove placeholder `.todo` blocks and the draft badge, then change the body to `data-draft="false"`.
5. Render the PDF, inspect every page, run the checker and package using your actual Brightspace group name.

```powershell
python -m analysis.run --prepare
python -m analysis.run --question 1
# Repeat for each completed question, through 12.
python -m report.render
python submission.py
python submission.py --package "Your group name"
```

Unimplemented questions exit with an error; they do not write fake results. Question completion records bind outputs to prepared data and analysis code. Rerun all implemented questions after editing their shared module. Report build records also bind the PDF to analysis outputs and local report assets; rerender after changing results or assets. The packager refuses incomplete/stale evidence or a draft PDF and never overwrites an existing ZIP. The archive includes test source so the documented checks can be rerun after extraction.

The checker verifies structure and provenance, not scientific correctness or writing quality. Use `SUBMISSION_CHECKLIST.md` before uploading. Each member separately writes at most 100 words using `report/individual-contribution.md`.

## Layout

- `crawler_src/`: direct Playwright crawler, consent task and shared input/domain helpers.
- `analysis/`: received-response preparation, explicit question tasks and generated outputs.
- `report/`: editable HTML, local PDF renderer and contribution template.
- `tests/`: deterministic unit tests plus opt-in local Chromium checks.
- `crawl_data_desktop`, `crawl_data_mobile`, `crawl_data_block`, `crawl_data_ignore`: real evidence only.

No web app, database, Docker, browser extension, haralyzer, parallel crawlers or remote consent services are used.
