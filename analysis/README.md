# Analysis contract

```text
python -m analysis.run --prepare
python -m analysis.run --question 1
```

Optional `--root PATH` selects another measurement root. The preparation step is implemented; Q1–Q7 and Q9–Q11 are implemented (`q1_per_visit.csv` + four `q1_*.png` box plots, `q2.csv`, `q3.csv` + two `q3_*.png` bar plots, `q4.csv`, `q5.csv` + two `q5_*.png` bar plots, `q6.csv`, `q7_<mode>.csv`, `q9.csv`, `q10.csv`, `q11.csv`); Q8 and Q12 still raise `NotImplementedError`. Q13 is written in the report. Keep each question clearly labeled when implementing it.

## Prepared datasets

`output/visits.csv`: site (original input domain), country, mode, final URL, first-party eTLD+1, received-request count and consent outcome. Completed visits with zero qualifying responses remain present. Failed visits never become zero-valued successes.

`output/requests.csv`: site, country, mode, final URL, request URL, hostname, eTLD+1, third-party flag, HTTP status, response headers, Disconnect categories, entities and session-replay flag. `response_headers`, `categories` and `entities` are JSON arrays inside CSV cells; load them with `json.loads`. Header arrays retain ordering, original casing and duplicates. Normalize names for comparisons, not values indiscriminately.

Only HTTP(S) entries with an HTTP response status 100–599 enter the dataset. A 404/500 is a response; status 0/missing response is excluded. Blocked requests are therefore excluded from all question results. Category prevalence considers all received requests unless the question specifically says third-party.

Third-partyness compares request eTLD+1 with the final main-page eTLD+1. Keep original site IDs for joining countries/ranks. Unknown entities have an empty array; do not count an invented “Unknown” entity. Report mapping coverage. Domains default to eTLD+1; Q12 additionally needs full hostnames.

`output/coverage.json` distinguishes completed, failed and pending visits. `output/provenance.json` binds the preparation to manifests, reference snapshots and loader code. Do not silently compare missing sites as zero. For final results, require all 120 completed visits.

## Question outputs

Each `qN(root)` returns a nonempty list of generated file Paths under `root/analysis/output`. Save numeric tables as CSV and plots as PNG. Plot axes must have titles. Use stable mode order Desktop, Mobile, Block, Ignore; country order NL, UK, US; break prevalence ties alphabetically by domain. If fewer than the requested top-N exist, show only observed rows and explain the shortfall.

`execute_question` records output/input/code hashes in `output/completion.json`. Rerun preparation after collection changes. Rerun all questions after edits to their shared source. Nothing should use the blocked-URL diagnostic log as received traffic.

Q6 takes **global** domain set differences over all sites before ranking by distinct-site count. Q7 unions categories for each reported eTLD+1 across observed hostnames. Q10 counts explicit empty allowlists, not missing headers or restrictive allowlists. Q11 must parse repeated/comma-separated ordered fallback tokens, using the last recognized policy, and select effective `no-referrer`.

## Tranco and DNS tasks

Fill `tranco.csv` using one dated, locally saved ranking snapshot. Columns: `domain,rank,snapshot_date`; domain is eTLD+1, rank is a positive integer or empty when absent, date is YYYY-MM-DD. Missing rank is NA, not zero. Record the list ID/source and retrieval date in the report. Do not call an online ranking API from analysis code.

For Q12 add and pin dnspython. Query first-party request subdomains during analysis, follow CNAME chains with a visited-name set and finite timeout/depth, and match each target against every Disconnect category. Record complete targets and their entities. Deduplicate rows per crawl; never discard DNS errors without accounting for them.

Save `output/dns_cache.json` keyed by lowercased queried hostname. Each value has `queried_at_utc`, `status` (`ok`, `no_cname`, `nxdomain`, `timeout`, `loop`, or `error`), `chain` (ordered objects with `source` and `target`) and `error` (text or null). Reuse the saved cache for reproducible report runs. DNS answers collected later can differ from those at crawl time; explain that limitation. The cache and Q12 code are intentionally not implemented yet.
