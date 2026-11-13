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

## Mobile completion — 13 November 2026

- Live probe of the Desktop handler on all 30 sites as a Pixel 10: 13 accepted, 7 not found, 10 failed. Causes: unrecognized acceptance labels ("I Accept Cookies", "Accept recommended settings", "I'm ok with that", "Accept all functional, advertising and performance cookies"), a tiered Essential/Standard/Complete prompt, emptied CMP wrappers still counted as prompts because hidden text was read, a wrapper that stays rendered after acceptance, a static footer notice far below the viewport, and banner detection taking 25 s on Cookiebot pages (one browser round trip per candidate element) against the 12 s budget.
- Fixes in `consent.py`, all generic: added the labels above (accept-all patterns stay preferred; generic labels stay disallowed when category controls are present), the "Complete" level counts as accept-all, prompts must be on screen and contain rendered consent text, dismissal accepts either the banner or the clicked control disappearing followed by the existing re-scan, banner detection runs in one evaluation per frame, and clicks may take up to 5 s for banners that slide in.
- Re-probe: 22 accepted, 8 not found, 0 failed. Every accepted before/after screenshot was reviewed. Not found: uu.nl, mit.edu, stanford.edu, harvard.edu, uchicago.edu, yale.edu and berkeley.edu show no banner; caltech.edu shows a notice whose only control is "Close", which is not consent (limitation).
- Full suite: 40 tests passed with OTP_BROWSER_TESTS=1. Five new consent regressions each fail against the previous handler.
- Mobile crawl: 29/30 complete (22 accepted, 7 not_found, matching the probe). yale.edu repeatedly fails in Chromium with net::ERR_CERT_COMMON_NAME_INVALID although Python TLS validates the certificates of both Yale server groups; rerun the same command to retry.
- `consent.py` is part of every crawl's identity, so Desktop, Block and Ignore must be crawled with this version before analysis.
