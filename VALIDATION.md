# Validation history

Verified on Windows with Python 3.12.14, Playwright 1.64.1 and Chromium 156.0.8078.4. The actual Pixel 10 descriptor is available. All Python package versions are frozen in requirements.txt; `pip check` reports no broken requirements.

## Results

- Full suite: **23 tests passed**, with `OTP_BROWSER_TESTS=1`; no skipped tests in the final run.
- Real local-browser checks: all four mode configurations, HAR/video finalization, viewport screenshots, tracker blocking, fresh cookies, bounded scrolling and PDF generation.
- Local Ignore roundtrip used the real required waits, resumed without another request, and prepared analysis data from the saved manifest/HAR.
- Interruption/resume, incompatible fingerprints, corrupt artifacts, domain matching, reference checksums, redirected sites, repeated headers, HTTP errors and zero-response visits are covered.
- A synthetic 120-visit fixture passed readiness and ZIP integrity checks. Synthetic measurements exist only inside temporary test fixtures, not the delivered crawl folders.
- Independent review findings were fixed with regression tests: mode/site identity validation, PDF invalidation after analysis/assets change, and inclusion of test source in the submission archive.
- Draft PDF has five pages, Q1–Q13 sections and visible draft labeling. All pages were visually reviewed.
- Empty-data preparation succeeds. Unfinished Q1 and accept-consent CLI commands fail explicitly. Submission readiness correctly fails for the uncollected dataset, unfinished analyses and draft report.

## Original foundation boundaries

At the original foundation handoff, no university websites had been crawled. Consent was then unfinished; the Desktop update implements it. Q1–Q12, DNS collection, final report prose and individual contributions remain unfinished. No Git repository was initialized. Tests used an isolated workspace environment; follow README.md to create your own environment.

The submission ZIP includes additional supporting source (report renderer and tests) alongside the assignment-required layout so the documented workflow works after extraction. The separately supplied foundation ZIP is a source handoff, **not a ready-to-submit assignment**.

## Desktop completion — 13 November 2026

- Implemented generic English/Dutch accept-all handling in visible consent prompts, frames and open shadow roots. Verifies dismissal; unsupported detected flows fail and retain evidence. Generic acceptance is disallowed in preference dialogs containing category controls.
- Final full suite: 35 tests passed with OTP_BROWSER_TESTS=1, including production Desktop consent, required waits, four evidence files and resume without revisiting.
- Sequential live smoke test: uva.nl, ru.nl and cam.ac.uk completed with accepted consent. After the final persistent-settings fix, ru.nl was rechecked successfully. This is smoke coverage, not the 30-site measurement.
- Independent review regressions fixed: persistent cookie wrappers/settings launchers and unchecked preferences falsely classified as all-consent.
- Fixed Git Windows CRLF checkout corruption of checksummed inputs with .gitattributes. Original reference checksums are unchanged.
- Recordings remain in local scratch storage, not Git. Q1–Q12 and the final report remain outside this Desktop change.
