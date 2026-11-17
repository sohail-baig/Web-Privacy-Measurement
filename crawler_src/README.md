# Online Tracking & Privacy — Assignment 2

Web privacy measurement of 30 university homepages (10 NL, 10 UK, 10 US) in four crawl modes. The crawler visits each site with Playwright (Chromium) and saves a HAR file, screenshots and a video. The analysis turns that data into the tables and plots for Q1–Q12, which are in `report.ipynb`.

## Install

Needs Python 3.12. From the project folder:

```
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m playwright install chromium
```

## Run the crawler

```
python crawler_src/crawl.py -m desktop -l sites.csv
python crawler_src/crawl.py -m mobile -l sites.csv
python crawler_src/crawl.py -m block -l sites.csv
python crawler_src/crawl.py -m ignore -l sites.csv
```

- `-m` is the crawl mode, `-l` the site list (`domain,country` per line).
- Results go to `crawl_data_<mode>/`: `<site>.har`, `<site>_pre_consent.png`, `<site>_post_consent.png` (not in ignore mode) and `<site>.webm`.
- If the crawler stops or a site fails, run the same command again. Finished sites are skipped (tracked in `manifest.json`).

| Mode | Browser | Cookies | Blocking |
|---|---|---|---|
| desktop | Chromium, 1366×768 | accept all | none |
| mobile | Chromium as Pixel 10 | accept all | none |
| block | Chromium, 1366×768 | accept all | Disconnect: Advertising, Analytics, Social, FingerprintingInvasive, FingerprintingGeneral |
| ignore | Chromium, 1366×768 | no interaction | none |

Each visit: load page → wait 10 s → accept cookies → wait 5 s → scroll to the bottom in steps → wait 5 s → close. Ignore mode skips the cookie step and its wait.

**Cookie banners:** `consent.py` looks for cookie/consent dialogs on the page (including iframes) and clicks an "accept all" style button, using English and Dutch keywords. It checks that the banner actually closed. No online services or browser extensions are used. If no banner is found the result is `not_found`; check those screenshots by hand.

## Run the analysis

```
python -m analysis.run --prepare
python -m analysis.run --question 1 2 3 4 5 6 7 8 9 10 11 12
```

`--prepare` reads the HAR files of all four crawls into `analysis/output/visits.csv` and `requests.csv`. Each question then saves its results in `analysis/output/`:

| Question | Files |
|---|---|
| Q1 | `q1_*.png` (4 box plots), `q1_per_visit.csv` |
| Q2, Q4, Q6, Q9, Q10, Q11 | `q2.csv`, `q4.csv`, `q6.csv`, `q9.csv`, `q10.csv`, `q11.csv` |
| Q3, Q5 | `q3.csv` / `q5.csv` plus `*_advertising.png` and `*_analytics.png` |
| Q7, Q12 | one CSV per mode: `q7_<mode>.csv`, `q12_<mode>.csv` |
| Q8 | `q8_highest_desktop.csv`, `q8_lowest_desktop.csv` |

Only requests that got a response are counted. A request is third-party when its domain (eTLD+1) differs from the visited page's domain. Tracker categories and companies come from Disconnect's lists in `crawler_src/reference_data/`. Q8 uses the Tranco ranks in `analysis/tranco.csv` (list from 14 November 2026). Q12 looks up CNAME records with dnspython and saves them in `analysis/output/dns_cache.json`, so later runs give the same results.

All four crawls were done on 13 November 2026 from the same laptop and network.
