"""Q1–Q12 are intentionally unfinished. Return a list of generated output Paths.

Read output/visits.csv and output/requests.csv; decode the three JSON-list columns.
Use visits as the denominator, including zero-request visits. Unknown entities are
not invented entities; report mapping coverage. Never count aborted requests.
Save CSV tables and PNG plots under output/, with deterministic ties by domain.
"""


def q1(root):
    raise NotImplementedError('Q1: four box plots by mode: requests, third-party requests, distinct third-party domains, distinct known third-party entities.')


def q2(root):
    raise NotImplementedError('Q2: min/median/max of the four Q1 metrics, grouped by mode.')


def q3(root):
    raise NotImplementedError('Q3: Advertising and Analytics bar plots; count distinct sites with at least one received response in each category, by mode.')


def q4(root):
    raise NotImplementedError('Q4: Desktop Q1 metric min/median/max grouped by NL, UK and US.')


def q5(root):
    raise NotImplementedError('Q5: Ignore Advertising and Analytics site-count bar plots grouped by country.')


def q6(root):
    raise NotImplementedError('Q6: globally Desktop-only and Mobile-only third-party domain set differences; top three by distinct-site prevalence in each direction.')


def q7(root):
    raise NotImplementedError('Q7: four top-ten third-party domain prevalence tables, including all Disconnect categories or NA.')


def q8(root):
    raise NotImplementedError('Q8: Desktop highest and lowest three sites by distinct third-party domains; join dated local Tranco ranks, country and counts.')


def q9(root):
    raise NotImplementedError('Q9: sites contacting session-replay domains, with country and all observed modes. Use metadata, not a category named session replay.')


def q10(root):
    raise NotImplementedError('Q10: five permissions most often explicitly disabled with () in Mobile first-party response Permissions-Policy headers; count distinct sites.')


def q11(root):
    raise NotImplementedError('Q11: Desktop sites with effective no-referrer in first-party response Referrer-Policy headers; parse ordered fallback policies and include country.')


def q12(root):
    raise NotImplementedError('Q12: add dnspython; follow first-party subdomain CNAME chains with timeouts/loop detection; cache timestamped answers/errors; match any Disconnect category and entity; four tables. See README.md for cache format.')


QUESTIONS = {1:q1, 2:q2, 3:q3, 4:q4, 5:q5, 6:q6, 7:q7, 8:q8, 9:q9, 10:q10, 11:q11, 12:q12}
