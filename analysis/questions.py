"""Assignment questions Q1–Q12 (Q8 and Q12 unfinished). Each returns a list of generated output Paths.

Read output/visits.csv and output/requests.csv; decode the three JSON-list columns.
Use visits as the denominator, including zero-request visits. Unknown entities are
not invented entities; report mapping coverage. Never count aborted requests.
Save CSV tables and PNG plots under output/, with deterministic ties by domain.
"""


import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')  # draw straight to PNG files, no window
import matplotlib.pyplot as plt
import pandas as pd
import dns.resolver, dns.exception


MODE_ORDER = ['desktop', 'mobile', 'block', 'ignore']
MODE_LABELS = {'desktop': 'Desktop', 'mobile': 'Mobile', 'block': 'Block', 'ignore': 'Ignore'}
COUNTRY_ORDER = ['NL', 'UK', 'US']

# The four per-visit numbers used by Q1, Q2 and Q4, with readable axis titles.
METRICS = ['requests', 'third_party_requests', 'third_party_domains', 'third_party_entities']
METRIC_TITLES = {
    'requests': 'Requests',
    'third_party_requests': 'Third-party requests',
    'third_party_domains': 'Distinct third-party domains',
    'third_party_entities': 'Distinct known third-party entities',
}


def load_prepared(root):
    """Return the output folder plus the prepared visits and requests tables."""
    output = Path(root) / 'analysis' / 'output'
    visits = pd.read_csv(output / 'visits.csv')
    requests = pd.read_csv(output / 'requests.csv')
    return output, visits, requests


def visit_metrics(visits, requests):
    """One row per visit with the four metrics.

    Visits are the denominator, so a visit without any request still counts (as zeros).
    Entities come only from third-party requests; unknown domains add no entity.
    """
    rows = []

    for _, visit in visits.iterrows():
        site_requests = requests[(requests['site'] == visit['site']) & (requests['mode'] == visit['mode'])]
        third_party = site_requests[site_requests['is_third_party'] == True]

        entities = set()

        for value in third_party['entities']:
            for entity in json.loads(value):
                entities.add(entity)

        rows.append({
            'site': visit['site'],
            'country': visit['country'].upper(),
            'mode': visit['mode'],
            'requests': len(site_requests),
            'third_party_requests': len(third_party),
            'third_party_domains': third_party['domain'].nunique(),
            'third_party_entities': len(entities)
        })

    return pd.DataFrame(rows, columns=['site', 'country', 'mode'] + METRICS)


def summary_table(data, column, order):
    """Min/median/max of every metric for each group, in a fixed order (observed groups only)."""
    rows = []

    for group in order:
        part = data[data[column] == group]
        if part.empty:
            continue

        row = {column: group, 'sites': len(part)}
        for metric in METRICS:
            row[metric + '_min'] = part[metric].min()
            row[metric + '_median'] = part[metric].median()
            row[metric + '_max'] = part[metric].max()
        rows.append(row)

    return pd.DataFrame(rows)


def observed_modes(visits):
    """Modes that have at least one completed visit, in the fixed order."""
    return [mode for mode in MODE_ORDER if (visits['mode'] == mode).any()]


def q1(root):
    """Q1: box plots by mode for each of the four metrics."""
    output, visits, requests = load_prepared(root)

    if visits.empty:
        raise ValueError('Q1: no completed visits in visits.csv. Crawl and run --prepare first.')

    data = visit_metrics(visits, requests)
    modes = observed_modes(visits)
    files = []

    # The numbers behind the plots, so every box can be checked.
    table = output / 'q1_per_visit.csv'
    data.assign(mode=data['mode'].map(MODE_LABELS)).to_csv(table, index=False)
    files.append(table)

    for metric in METRICS:
        figure, axis = plt.subplots(figsize=(6, 4.5))
        axis.boxplot([data[data['mode'] == mode][metric] for mode in modes],
                     tick_labels=[MODE_LABELS[mode] for mode in modes])
        axis.set_title(f'{METRIC_TITLES[metric]} per website visit')
        axis.set_xlabel('Crawl mode')
        axis.set_ylabel(METRIC_TITLES[metric])
        axis.set_ylim(bottom=0)
        figure.tight_layout()

        file = output / f'q1_{metric}.png'
        figure.savefig(file, dpi=150)
        plt.close(figure)
        files.append(file)

    return files


def q2(root):
    """Q2: min/median/max of the four Q1 metrics, grouped by mode."""
    output, visits, requests = load_prepared(root)

    if visits.empty:
        raise ValueError('Q2: no completed visits in visits.csv. Crawl and run --prepare first.')

    result = summary_table(visit_metrics(visits, requests), 'mode', MODE_ORDER)
    result['mode'] = result['mode'].map(MODE_LABELS)

    file = output / 'q2.csv'
    result.to_csv(file, index=False)

    return [file]


CATEGORIES = ['Advertising', 'Analytics']


def category_sites(visits, requests, column, groups):
    """Per group: visited sites and distinct sites with a received response in each category.

    All received requests count (first- and third-party), as the analysis README says.
    """
    rows = []

    for group in groups:
        group_requests = requests[requests[column] == group]
        row = {column: group, 'sites_visited': int((visits[column] == group).sum())}
        for category in CATEGORIES:
            matches = group_requests['categories'].map(lambda value: category in json.loads(value))
            row[category.lower() + '_sites'] = group_requests[matches]['site'].nunique()
        rows.append(row)

    return pd.DataFrame(rows)


def category_bar_plots(result, column, xlabel, file_prefix, title_suffix=''):
    """One bar plot per category from a category_sites() table; the y axis spans the visited sites."""
    files = []

    for category in CATEGORIES:
        figure, axis = plt.subplots(figsize=(6, 4.5))
        bars = axis.bar(result[column], result[category.lower() + '_sites'], color='#4C72B0')
        axis.bar_label(bars)
        axis.set_title(f'Websites contacting {category} domains{title_suffix}')
        axis.set_xlabel(xlabel)
        axis.set_ylabel('Number of websites')
        axis.set_ylim(0, max(result['sites_visited'].max(), 1))
        axis.yaxis.get_major_locator().set_params(integer=True)
        figure.tight_layout()

        file = Path(f'{file_prefix}_{category.lower()}.png')
        figure.savefig(file, dpi=150)
        plt.close(figure)
        files.append(file)

    return files


def q3(root):
    """Q3: per mode, distinct sites with at least one received Advertising / Analytics response."""
    output, visits, requests = load_prepared(root)

    if visits.empty:
        raise ValueError('Q3: no completed visits in visits.csv. Crawl and run --prepare first.')

    result = category_sites(visits, requests, 'mode', observed_modes(visits))
    result['mode'] = result['mode'].map(MODE_LABELS)

    table = output / 'q3.csv'
    result.to_csv(table, index=False)

    return [table] + category_bar_plots(result, 'mode', 'Crawl mode', output / 'q3')


def q4(root):
    """Q4: Desktop min/median/max of the four Q1 metrics, grouped by country."""
    output, visits, requests = load_prepared(root)

    visits = visits[visits['mode'] == 'desktop']
    requests = requests[requests['mode'] == 'desktop']

    if visits.empty:
        raise ValueError('Q4: no completed Desktop visits in visits.csv. Crawl desktop and run --prepare first.')

    result = summary_table(visit_metrics(visits, requests), 'country', COUNTRY_ORDER)

    file = output / 'q4.csv'
    result.to_csv(file, index=False)

    return [file]


def q5(root):
    """Q5: Ignore mode, distinct sites with a received Advertising / Analytics response, by country."""
    output, visits, requests = load_prepared(root)

    visits = visits[visits['mode'] == 'ignore']
    requests = requests[requests['mode'] == 'ignore']

    if visits.empty:
        raise ValueError('Q5: no completed Ignore visits in visits.csv. Crawl ignore and run --prepare first.')

    countries = [country for country in COUNTRY_ORDER if (visits['country'] == country.lower()).any()]
    result = category_sites(visits, requests, 'country', [country.lower() for country in countries])
    result['country'] = result['country'].str.upper()

    table = output / 'q5.csv'
    result.to_csv(table, index=False)

    return [table] + category_bar_plots(result, 'country', 'Country', output / 'q5', ' (Ignore mode)')


def third_party_sites(requests, mode):
    """Third-party eTLD+1 -> number of distinct sites contacting it in one mode."""
    rows = requests[(requests['mode'] == mode) & (requests['is_third_party'] == True)]
    return rows.groupby('domain')['site'].nunique()


def most_prevalent(counts, limit):
    """(domain, sites) pairs, most sites first; ties alphabetical by domain."""
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]


def q6(root):
    """Q6: third-party domains seen only on Desktop or only on Mobile (over all sites), top three each."""
    output, visits, requests = load_prepared(root)

    if not {'desktop', 'mobile'} <= set(visits['mode']):
        raise ValueError('Q6: needs completed Desktop and Mobile visits. Crawl both and run --prepare first.')

    desktop = third_party_sites(requests, 'desktop')
    mobile = third_party_sites(requests, 'mobile')
    rows = []

    # Global set difference first, then rank what is left by distinct-site prevalence.
    for label, own, other in (('Desktop only', desktop, mobile), ('Mobile only', mobile, desktop)):
        exclusive = own[~own.index.isin(other.index)]
        for domain, sites in most_prevalent(exclusive, 3):
            rows.append({'exclusive_to': label, 'domain': domain, 'sites': sites})

    file = output / 'q6.csv'
    pd.DataFrame(rows, columns=['exclusive_to', 'domain', 'sites']).to_csv(file, index=False)

    return [file]


def q7(root):
    """Q7: per mode, the ten third-party domains contacted by most sites, with all Disconnect categories."""
    output, visits, requests = load_prepared(root)

    if visits.empty:
        raise ValueError('Q7: no completed visits in visits.csv. Crawl and run --prepare first.')

    files = []

    for mode in observed_modes(visits):
        rows = requests[(requests['mode'] == mode) & (requests['is_third_party'] == True)]
        # Union of categories over every observed hostname of the eTLD+1.
        categories = rows.groupby('domain')['categories'].agg(
            lambda values: sorted({category for value in values for category in json.loads(value)}))

        table = [{'rank': rank, 'domain': domain, 'sites': sites,
                  'categories': '; '.join(categories[domain]) or 'NA'}
                 for rank, (domain, sites) in enumerate(most_prevalent(third_party_sites(requests, mode), 10), 1)]

        file = output / f'q7_{mode}.csv'
        pd.DataFrame(table, columns=['rank', 'domain', 'sites', 'categories']).to_csv(file, index=False)
        files.append(file)

    return files



def sites_to_third_party(requests, mode):
    """Website -> number of distinct third-party domains contacted in one mode"""
    rows = requests[(requests['mode'] == mode) & (requests['is_third_party'] == True)]
    return rows.groupby('site')['domain'].nunique()

def frequency(counts, limit):
    """Return the highest or lowest counts"""
    if limit > 0:
        return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    else:
        return sorted(counts.items(), key=lambda item: (item[1], item[0]))[:abs(limit)]


def q8(root):
    """Q8: Mode Desktop: highest and lowest three sites by distinct third-party domains; join dated local Tranco ranks, country and counts."""
    output, visits, requests = load_prepared(root)
    mode = "desktop"
    if visits.empty:
        raise ValueError("Q8: no completed Desktop visits in visits.csv. Crawl desktop and run --prepare first.")

    files = []
    
    two_table = {"highest":3, "lowest":-3}
    tranco = pd.read_csv(root / 'analysis/tranco.csv')
    visits = visits[visits["mode"] == mode]
    requests = requests[requests["mode"] == mode]
    
    amount = sites_to_third_party(requests, mode)

    for k,v in two_table.items():
        table = []
        top_or_bottom = frequency(amount, v)
        for domain, count in top_or_bottom:
            country = (visits[visits['site'] == domain].iloc[0]['country'])
            rank = tranco[tranco['domain'] == domain].iloc[0]['rank']

            table.append({
                    'Website': domain,
                    'Tranco rank': rank,
                    'Country': country,
                    'Number of distinct third-party domains': count
            })
            
        file = output / f'q8_{k}_desktop.csv'
        pd.DataFrame(table, columns=['Website', 'Tranco rank', 'Country', 'Number of distinct third-party domains']).to_csv(file, index=False)
        files.append(file)

    return files



def q9(root):
    """Q9: sites contacting session-replay domains (Disconnect metadata), with country and observed modes."""
    output, visits, requests = load_prepared(root)

    if visits.empty:
        raise ValueError('Q9: no completed visits in visits.csv. Crawl and run --prepare first.')

    replay = requests[requests['session_replay'] == True]
    rows = []

    for (site, domain), group in replay.groupby(['site', 'domain']):
        modes = [MODE_LABELS[mode] for mode in MODE_ORDER if mode in set(group['mode'])]
        rows.append({'site': site, 'country': group['country'].iloc[0].upper(),
                     'session_replay_domain': domain, 'modes': ', '.join(modes)})

    rows.sort(key=lambda row: (COUNTRY_ORDER.index(row['country']), row['site'], row['session_replay_domain']))

    file = output / 'q9.csv'
    pd.DataFrame(rows, columns=['site', 'country', 'session_replay_domain', 'modes']).to_csv(file, index=False)

    return [file]


def header_values(headers, name):
    """Values of every header called name (case-insensitive) in a JSON-encoded HAR header list, in order."""
    return [header['value'] for header in json.loads(headers) if header['name'].lower() == name]


def disabled_permissions(value):
    """Features given an explicit empty allowlist, e.g. 'camera=(), geolocation=(self)' -> {'camera'}."""
    disabled = set()

    for member in value.split(','):
        feature, _, allowlist = member.partition('=')
        # Structured-field inner lists may contain spaces: "( )" is empty too.
        if allowlist.replace(' ', '') == '()':
            disabled.add(feature.strip().lower())

    return disabled


def q10(root):
    """Q10: five permissions most often disabled with () in Mobile first-party Permissions-Policy headers."""
    output, visits, requests = load_prepared(root)

    if not (visits['mode'] == 'mobile').any():
        raise ValueError('Q10: no completed Mobile visits in visits.csv. Crawl mobile and run --prepare first.')

    first_party = requests[(requests['mode'] == 'mobile') & (requests['is_third_party'] == False)]
    sites_by_permission, senders = {}, set()

    for site, headers in zip(first_party['site'], first_party['response_headers']):
        for value in header_values(headers, 'permissions-policy'):
            senders.add(site)
            for permission in disabled_permissions(value):
                sites_by_permission.setdefault(permission, set()).add(site)

    counts = {permission: len(sites) for permission, sites in sites_by_permission.items()}
    rows = [{'permission': permission, 'sites': sites, 'sites_sending_header': len(senders)}
            for permission, sites in most_prevalent(counts, 5)]

    file = output / 'q10.csv'
    pd.DataFrame(rows, columns=['permission', 'sites', 'sites_sending_header']).to_csv(file, index=False)

    return [file]


REFERRER_POLICIES = {'no-referrer', 'no-referrer-when-downgrade', 'same-origin', 'origin', 'strict-origin',
                     'origin-when-cross-origin', 'strict-origin-when-cross-origin', 'unsafe-url'}


def effective_referrer_policy(values):
    """The policy a browser applies: the last recognized token over repeated, comma-separated values.

    Unknown tokens are skipped, so 'no-referrer, future-policy' still means no-referrer.
    """
    tokens = [token.strip().lower() for value in values for token in value.split(',')]
    recognized = [token for token in tokens if token in REFERRER_POLICIES]
    return recognized[-1] if recognized else None


def q11(root):
    """Q11: Desktop sites where a first-party response sets an effective no-referrer policy."""
    output, visits, requests = load_prepared(root)

    if not (visits['mode'] == 'desktop').any():
        raise ValueError('Q11: no completed Desktop visits in visits.csv. Crawl desktop and run --prepare first.')

    first_party = requests[(requests['mode'] == 'desktop') & (requests['is_third_party'] == False)]
    responses = {}

    for site, country, headers in zip(first_party['site'], first_party['country'], first_party['response_headers']):
        if effective_referrer_policy(header_values(headers, 'referrer-policy')) == 'no-referrer':
            key = (site, country.upper())
            responses[key] = responses.get(key, 0) + 1

    rows = [{'site': site, 'country': country, 'no_referrer_responses': count}
            for (site, country), count in sorted(responses.items(), key=lambda item: (COUNTRY_ORDER.index(item[0][1]), item[0][0]))]

    file = output / 'q11.csv'
    pd.DataFrame(rows, columns=['site', 'country', 'no_referrer_responses']).to_csv(file, index=False)

    return [file]

def load_entities(root):
    with open(root / "analysis/entities.json", encoding="utf-8") as f:
        data = json.load(f)

    domain_to_entity = {}

    for entity, i in data["entities"].items():
        for domain in i["properties"] + i["resources"]:
            domain_to_entity.setdefault(domain, set()).add(entity)

    return domain_to_entity

def load_blocklist(root):
    with open(root / "analysis/services.json", encoding='utf-8') as f:
        services = json.load(f)

    lookup = {}

    for category, entries in services["categories"].items():
        for entry in entries:
            entity, websites = next(iter(entry.items()))

            for domains in websites.values():
                for domain in domains:
                    lookup.setdefault(domain, {}).setdefault(entity, set()).add(category)
    return lookup

def load_dns_cache(output):
    file = output / "dns_cache.json"

    if file.exists():
        with open(file, encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_dns_cache(output, cache):
    file = output / "dns_cache.json"

    with open(file, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=4)

def cname_chain(hostname, timeout=5, max_chain=20):
    hostname = hostname.lower().rstrip('.')
    visited = {hostname}
    chain = []
    current = hostname

    result = {
        "queried_at_utc": str(pd.Timestamp.now(tz="Europe/Amsterdam")),
        "status": None,
        "chain": [],
        "error": None
    }

    resolver = dns.resolver.Resolver()

    try:
        for _ in range(max_chain):
            answer = resolver.resolve(current,"CNAME",
                lifetime=timeout,
                search=False,
                raise_on_no_answer=False
            )

            if answer.rrset == None:
                result["status"] = "ok" if chain else "no_cname"
                break
            
            target = str(answer.rrset[0].target).lower().rstrip('.')

            chain.append({
                "source": current,
                "target": target
            })
            
            if target in visited:
                result["status"] = "loop"
                result["error"] = f"CNAME loop detected: {target}"
                break

            visited.add(target)
            current = target
            
        else:
            result["status"] = "error"
            result["error"] = "Maximum chain depth reached"
        
    except dns.resolver.NXDOMAIN as e:
        result["status"] = "nxdomain"
        result["error"] = str(e)
    except dns.exception.Timeout as e:
        result["status"] = "timeout"
        result["error"] = str(e)
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)

    result["chain"] = chain
    return result

def get_dns_result(hostname, cache):
    hostname = hostname.lower().rstrip('.')
    if hostname not in cache:
        cache[hostname] = cname_chain(hostname)

    return cache[hostname]

def match_blocklist(target, domain_lookup, entity_lookup):
    target = target.lower().rstrip('.')
    return [
        (entity, sorted(categories))
        for domain, categories in domain_lookup.items()
        if target == domain or target.endswith('.' + domain)
        for entity in entity_lookup.get(domain, {'Unknown'})]
     

def q12(root):
    output, visits, requests = load_prepared(root)

    if visits.empty:
        raise ValueError('Q12: no completed visits in visits.csv. Crawl and run --prepare first.')

    files = []
    domain_lookup = load_blocklist(root)
    entity_lookup = load_entities(root)
    cache = load_dns_cache(output)

    #print(domain_lookup)

    for mode in observed_modes(visits):
        first_party = visits[visits['mode'] == mode][['site', 'first_party_domain']].drop_duplicates('site')
        rows = requests[(requests['mode'] == mode) & (requests['is_third_party'] == False)].merge(first_party,how="left",on="site")

        #Keep only actual first-party /subdomains/
        rows = rows[
            rows.apply(
                lambda r: pd.notna(r['hostname']) and
                pd.notna(r['first_party_domain']) and
                r['hostname'].rstrip('.').endswith('.' + r['first_party_domain'].rstrip('.')),
                axis=1)
        ]

        hostnames = rows['hostname'].dropna().str.lower().str.rstrip('.').unique()
        
        table = []

        for hostname in hostnames:
            result = get_dns_result(hostname, cache)

            table.extend([
                {
                    "First-party subdomain": hostname,
                    "CNAME record": link["target"].lower().rstrip('.'),
                    "CNAME entity": entity,
                    "Disconnect categories": ', '.join(categories)
                }
                for link in result["chain"]
                for entity, categories in match_blocklist(link['target'], domain_lookup, entity_lookup)
            ])

        file = output / f'q12_{mode}.csv'

        pd.DataFrame(table, columns=['First-party subdomain', 'CNAME record', 'CNAME entity', 'Disconnect categories']).drop_duplicates().to_csv(file, index=False)
        files.append(file)

    save_dns_cache(output, cache)

    return files

QUESTIONS = {1:q1, 2:q2, 3:q3, 4:q4, 5:q5, 6:q6, 7:q7, 8:q8, 9:q9, 10:q10, 11:q11, 12:q12}
