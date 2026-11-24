import os
import re
import html
import smtplib
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET
from email.message import EmailMessage
from urllib.parse import quote_plus, urlsplit
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

UTC = timezone.utc
IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime.now(UTC)
CUTOFF = NOW - timedelta(hours=24)
MAX_DATED = 35
MAX_UNDATED = 12

CORE_TERMS = [".net", "dotnet", "c#", "c sharp", "csharp", "asp.net", "aspnet"]
ROLE_TERMS = [
    "software engineer", "software developer", ".net developer", "dotnet developer",
    "c# developer", "backend engineer", "backend developer", "asp.net developer",
    "api developer", "application developer"
]
SKILLS = [
    "c#", ".net", "asp.net core", "web api", "ef core", "entity framework",
    "sql server", "azure functions", "azure app service", "azure blob storage",
    "azure", "azure ad", "jwt", "rbac", "key vault", "application insights",
    "nunit", "in-memory caching", "polly", "cosmos db", "azure data factory",
    "rest api", "microservices", "linq", "ado.net", "system design"
]
TARGET_TITLE_TERMS = [
    ".net developer", "dotnet developer", "c# developer", "asp.net core developer",
    "backend engineer", "backend developer", "software engineer", "software developer"
]

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "TharunPersonalJobSearch/2.0 (daily job discovery; respectful API use)"
})
retry = Retry(
    total=2, connect=2, read=2, backoff_factor=0.5,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset(["GET", "POST"])
)
SESSION.mount("https://", HTTPAdapter(max_retries=retry))


def clean_text(value):
    value = html.unescape(str(value or ""))
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def parse_date(value):
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)) or str(value).strip().isdigit():
            stamp = float(value)
            if stamp > 10**12:
                stamp /= 1000.0
            return datetime.fromtimestamp(stamp, tz=UTC)
        raw = str(value).strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            parsed = parsedate_to_datetime(str(value))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def fetch_json(url, params=None, headers=None, method="GET", payload=None, timeout=30):
    if method == "POST":
        response = SESSION.post(url, json=payload, params=params, headers=headers, timeout=timeout)
    else:
        response = SESSION.get(url, params=params, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.json()


def location_allowed(location, description=""):
    loc = (location or "").lower()
    combined = loc + " " + (description or "").lower()
    # Missing location is retained but visibly marked for manual verification.
    if not loc.strip() or loc.strip() == "not specified":
        return True
    wanted = ("hyderabad", "india", "remote", "anywhere", "worldwide", "global")
    if any(token in combined for token in wanted):
        # Exclude explicitly country-restricted remote roles outside India.
        foreign_restrictions = (
            "united states only", "us only", "usa only", "canada only",
            "uk only", "united kingdom only", "europe only", "australia only"
        )
        if "remote" in combined and any(x in combined for x in foreign_restrictions) and "india" not in combined:
            return False
        return True
    return False


def add_job(rows, source, title, company, location, url, description="", posted_date=None,
            salary=None, indexed_freshness=False):
    title = clean_text(title)
    description = clean_text(description)
    url = str(url or "").strip()
    if not title or not url or not url.startswith(("http://", "https://")):
        return

    combined = (title + " " + description).lower()
    has_core_stack = any(term in combined for term in CORE_TERMS)
    has_backend_azure = (
        "azure" in combined and
        any(term in combined for term in ("backend", "back-end", "web api", "rest api", "software engineer"))
    )
    if not (has_core_stack or has_backend_azure):
        return

    if re.search(r"\b(intern|internship|fresher|trainee|graduate trainee)\b", title, re.I):
        return

    raw_location = clean_text(location)
    if not location_allowed(raw_location, description):
        return
    location = raw_location or "Not specified — verify eligibility"

    posted = parse_date(posted_date)
    if posted and posted < CUTOFF:
        return

    skill_hits = sorted({skill for skill in SKILLS if skill in combined})
    title_lower = title.lower()
    title_hits = [term for term in TARGET_TITLE_TERMS if term in title_lower]

    score = 25
    score += min(45, len(skill_hits) * 5)
    score += 18 if any(term in title_lower for term in TARGET_TITLE_TERMS[:5]) else (10 if title_hits else 0)
    loc = location.lower()
    score += 15 if "hyderabad" in loc else (12 if "remote" in loc else (8 if "india" in loc else 0))
    if posted:
        score += 10
    if re.search(r"\b(3|4|5)\s*(\+|to|-)?\s*(years|yrs)\b", combined):
        score += 5
    score = min(100, score)

    if posted:
        posted_label = posted.astimezone(IST).strftime("%d %b %Y, %I:%M %p IST")
    elif indexed_freshness:
        posted_label = "Search index filtered to past 24h; verify original posting date"
    else:
        posted_label = "Posting date not provided; verify before applying"

    rows.append({
        "score": score,
        "source": source,
        "title": title,
        "company": clean_text(company) or "Not identified",
        "location": location,
        "url": url,
        "posted_dt": posted.isoformat() if posted else "",
        "posted_label": posted_label,
        "skills": ", ".join(skill_hits[:12]) or "Relevant .NET/Azure terms found",
        "salary": clean_text(salary) or "Not disclosed",
        "description": description[:650]
    })


def safe_error(exc):
    message = str(exc)
    for name in ("JOOBLE_API_KEY", "ADZUNA_APP_ID", "ADZUNA_APP_KEY", "BRAVE_SEARCH_API_KEY"):
        secret = os.getenv(name)
        if secret:
            message = message.replace(secret, "[redacted]")
    message = re.sub(r"(?i)(app_id|app_key|api_key|key)=([^&\\s]+)", r"\\1=[redacted]", message)
    return message[:180]


def portal_company(url):
    try:
        host = urlsplit(url).netloc.lower().removeprefix("www.")
        return host or "Search result"
    except Exception:
        return "Search result"


def collect_remoteok(rows):
    data = fetch_json("https://remoteok.com/api")
    for job in data:
        if not isinstance(job, dict) or not job.get("position"):
            continue
        add_job(rows, "Remote OK", job.get("position"), job.get("company"),
                job.get("location"), job.get("url") or job.get("apply_url"),
                job.get("description"), job.get("date") or job.get("epoch"),
                job.get("salary"))


def collect_arbeitnow(rows):
    data = fetch_json("https://www.arbeitnow.com/api/job-board-api")
    for job in data.get("data", []):
        add_job(rows, "Arbeitnow", job.get("title"), job.get("company_name"),
                job.get("location"), job.get("url"), job.get("description"),
                job.get("created_at"), job.get("salary"))


def collect_jobicy(rows):
    data = fetch_json("https://jobicy.com/api/v2/remote-jobs", params={"count": 50})
    for job in data.get("jobs", []):
        add_job(rows, "Jobicy", job.get("jobTitle"), job.get("companyName"),
                job.get("jobGeo"), job.get("url"), job.get("jobDescription"),
                job.get("pubDate"), job.get("annualSalary") or job.get("salary"))


def collect_weworkremotely(rows):
    # WWR explicitly publishes this public RSS feed for reuse with source attribution.
    response = SESSION.get("https://weworkremotely.com/categories/remote-programming-jobs.rss",
                           timeout=30)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    for item in root.findall(".//item"):
        add_job(rows, "We Work Remotely", item.findtext("title"), "",
                "Remote — country eligibility verify", item.findtext("link"),
                item.findtext("description"), item.findtext("pubDate"))


def collect_greenhouse(rows):
    slugs = os.getenv("GREENHOUSE", "").split()
    if not slugs:
        return "not configured"
    for slug in slugs:
        data = fetch_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
                          params={"content": "true"})
        for job in data.get("jobs", []):
            add_job(rows, "Greenhouse", job.get("title"), slug,
                    (job.get("location") or {}).get("name"), job.get("absolute_url"),
                    job.get("content"), job.get("updated_at"))


def collect_lever(rows):
    slugs = os.getenv("LEVER", "").split()
    if not slugs:
        return "not configured"
    for slug in slugs:
        data = fetch_json(f"https://api.lever.co/v0/postings/{slug}", params={"mode": "json"})
        for job in data:
            categories = job.get("categories") or {}
            loc = categories.get("location") or ", ".join(categories.get("allLocations") or [])
            add_job(rows, "Lever", job.get("text"), slug, loc, job.get("hostedUrl"),
                    job.get("descriptionPlain"), job.get("createdAt"), job.get("salaryRange"))


def collect_ashby(rows):
    boards = os.getenv("ASHBY", "").split()
    if not boards:
        return "not configured"
    for board in boards:
        data = fetch_json(f"https://api.ashbyhq.com/posting-api/job-board/{board}",
                          params={"includeCompensation": "true"})
        for job in data.get("jobs", []):
            locations = [job.get("location", "")]
            locations += [x.get("location", "") for x in job.get("secondaryLocations", [])]
            if job.get("isRemote"):
                locations.append("Remote")
            compensation = job.get("compensation") or {}
            salary = compensation.get("scrapeableCompensationSalarySummary") or compensation.get("compensationTierSummary")
            add_job(rows, "Ashby", job.get("title"), board, " / ".join(filter(None, locations)),
                    job.get("applyUrl") or job.get("jobUrl"),
                    job.get("descriptionPlain") or job.get("descriptionHtml"),
                    job.get("publishedAt"), salary)


def collect_smartrecruiters(rows):
    companies = os.getenv("SMARTRECRUITERS", "").split()
    if not companies:
        return "not configured"
    for company_id in companies:
        data = fetch_json(
            f"https://api.smartrecruiters.com/v1/companies/{company_id}/postings",
            params={"limit": 100, "offset": 0, "country": "IN", "destination": "PUBLIC"}
        )
        postings = data.get("content") or data.get("results") or data.get("postings") or []
        for job in postings:
            loc = job.get("location") or {}
            location = ", ".join(filter(None, [
                loc.get("city"), loc.get("region"), loc.get("country")
            ])) if isinstance(loc, dict) else str(loc)
            refs = job.get("ref") or {}
            url = job.get("applyUrl") or refs.get("jobAd") or refs.get("jobAdUrl")
            if not url and job.get("id"):
                url = f"https://careers.smartrecruiters.com/{company_id}/{job['id']}"
            add_job(rows, "SmartRecruiters", job.get("name") or job.get("title"),
                    company_id, location, url, job.get("jobAd") or job.get("description"),
                    job.get("releasedDate") or job.get("postedDate"))


def collect_adzuna(rows):
    app_id = os.getenv("ADZUNA_APP_ID")
    app_key = os.getenv("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        return "not configured"
    for page in (1, 2):
        data = fetch_json(
            f"https://api.adzuna.com/v1/api/jobs/in/search/{page}",
            params={
                "app_id": app_id, "app_key": app_key, "results_per_page": 50,
                "what": '"C#" .NET ASP.NET Core Azure developer',
                "where": "Hyderabad", "max_days_old": 1, "sort_by": "date",
                "sort_dir": "down", "content-type": "application/json"
            }
        )
        for job in data.get("results", []):
            company = (job.get("company") or {}).get("display_name")
            location = (job.get("location") or {}).get("display_name")
            salary = None
            if job.get("salary_min") or job.get("salary_max"):
                salary = f"INR {job.get('salary_min', '?')} - {job.get('salary_max', '?')} per year"
            add_job(rows, "Adzuna", job.get("title"), company, location,
                    job.get("redirect_url"), job.get("description"), job.get("created"), salary)


def collect_jooble(rows):
    api_key = os.getenv("JOOBLE_API_KEY")
    if not api_key:
        return "not configured"
    for location in ("Hyderabad", "India Remote"):
        data = fetch_json(
            f"{os.getenv('JOOBLE_API_BASE_URL', 'https://in.jooble.org/api').rstrip('/')}/{api_key}", method="POST",
            payload={
                "keywords": ".NET C# ASP.NET Core Azure backend developer",
                "location": location, "page": 1, "ResultOnPage": 50
            }
        )
        for job in data.get("jobs", []):
            add_job(rows, "Jooble", job.get("title"), job.get("company"),
                    job.get("location"), job.get("link"), job.get("snippet"),
                    job.get("updated") or job.get("updatedAt"), job.get("salary"))


BRAVE_QUERIES = [
    '(".NET Developer" OR "C# Developer" OR "ASP.NET Core") Hyderabad India jobs',
    '(".NET" OR "C#" OR "ASP.NET Core") Azure backend remote India jobs',
    'site:linkedin.com/jobs/view OR site:naukri.com OR site:in.indeed.com .NET C# developer Hyderabad',
    'site:foundit.in OR site:hirist.tech OR site:cutshort.io OR site:instahyre.com .NET developer India'
]


def collect_brave_search(rows):
    api_key = os.getenv("BRAVE_SEARCH_API_KEY")
    if not api_key:
        return "not configured"
    headers = {"X-Subscription-Token": api_key, "Accept": "application/json"}
    for query in BRAVE_QUERIES:
        data = fetch_json(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "freshness": "pd", "country": "IN",
                    "search_lang": "en", "count": 20},
            headers=headers
        )
        for result in (data.get("web") or {}).get("results", []):
            title = result.get("title")
            url = result.get("url")
            description = result.get("description", "")
            source = "Web Search (" + portal_company(url) + ")"
            add_job(rows, source, title, portal_company(url), "",
                    url, description, result.get("page_age"),
                    indexed_freshness=True)


def collect():
    rows = []
    statuses = {}

    collectors = [
        ("Remote OK", lambda: collect_remoteok(rows)),
        ("Arbeitnow", lambda: collect_arbeitnow(rows)),
        ("Jobicy", lambda: collect_jobicy(rows)),
        ("We Work Remotely", lambda: collect_weworkremotely(rows)),
        ("Greenhouse", lambda: collect_greenhouse(rows)),
        ("Lever", lambda: collect_lever(rows)),
        ("Ashby", lambda: collect_ashby(rows)),
        ("SmartRecruiters", lambda: collect_smartrecruiters(rows)),
        ("Adzuna", lambda: collect_adzuna(rows)),
        ("Jooble", lambda: collect_jooble(rows)),
        ("Brave web search", lambda: collect_brave_search(rows))
    ]

    for name, collector in collectors:
        before = len(rows)
        try:
            result = collector()
            if result == "not configured":
                statuses[name] = "Not configured (optional)"
            else:
                statuses[name] = f"OK — {len(rows) - before} relevant jobs"
        except Exception as exc:
            statuses[name] = f"FAILED — {type(exc).__name__}: {safe_error(exc)}"
            print(f"[{name}] {statuses[name]}")

    # De-duplicate identical application pages while keeping the strongest listing.
    unique = {}
    for job in rows:
        key = job["url"].split("#", 1)[0].rstrip("/")
        if key not in unique or job["score"] > unique[key]["score"]:
            unique[key] = job
    jobs = list(unique.values())
    jobs.sort(key=lambda j: (
        0 if j["posted_dt"] else 1,
        -j["score"],
        j["posted_dt"] or ""
    ), reverse=False)
    return jobs, statuses


def search_links():
    query = quote_plus('(".NET Developer" OR "C# Developer" OR "ASP.NET Core")')
    google_query = quote_plus('(".NET Developer" OR "C# Developer" OR "ASP.NET Core") Hyderabad India jobs')
    site_query = quote_plus('site:foundit.in OR site:hirist.tech OR site:cutshort.io OR site:instahyre.com .NET developer India')
    return [
        ("LinkedIn Hyderabad — last 24 hours",
         "https://www.linkedin.com/jobs/search/?keywords=.NET%20C%23%20Azure&location=Hyderabad&f_TPR=r86400"),
        ("LinkedIn Remote — last 24 hours",
         "https://www.linkedin.com/jobs/search/?keywords=.NET%20C%23%20Azure&location=India&f_TPR=r86400"),
        ("Naukri — .NET Hyderabad",
         "https://www.naukri.com/dot-net-developer-jobs-in-hyderabad"),
        ("Indeed — Hyderabad, last 24 hours",
         "https://in.indeed.com/jobs?q=.NET+C%23+Azure&l=Hyderabad&fromage=1"),
        ("Google Jobs — .NET / C# Hyderabad",
         "https://www.google.com/search?q=" + google_query + "&udm=8"),
        ("Foundit / Hirist / Cutshort / Instahyre search",
         "https://www.google.com/search?q=" + site_query),
        ("Company career pages — .NET / Azure Hyderabad",
         "https://www.google.com/search?q=" + quote_plus('".NET" Azure developer Hyderabad careers jobs'))
    ]


def main():
    jobs, statuses = collect()
    recent = [j for j in jobs if j["posted_dt"]]
    undated = [j for j in jobs if not j["posted_dt"]]
    recent.sort(key=lambda j: (j["score"], j["posted_dt"]), reverse=True)
    undated.sort(key=lambda j: j["score"], reverse=True)
    recent = recent[:MAX_DATED]
    undated = undated[:MAX_UNDATED]

    recipient = os.environ.get("JOB_ALERT_TO") or os.environ.get("SMTP_USER")
    sender = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_APP_PASSWORD")
    if not recipient or not sender or not password:
        raise SystemExit("Missing SMTP_USER or SMTP_APP_PASSWORD GitHub secret.")

    local_now = NOW.astimezone(IST)
    total = len(recent) + len(undated)
    msg = EmailMessage()
    msg["Subject"] = (
        f"Daily .NET/Azure job radar — {local_now.strftime('%d %b %Y')} "
        f"({len(recent)} dated + {len(undated)} undated matches)"
    )
    msg["From"] = sender
    msg["To"] = recipient

    lines = [
        f"THARUN'S DAILY .NET / C# / AZURE JOB RADAR — {local_now.strftime('%d %b %Y %I:%M %p IST')}",
        "",
        f"Relevant leads found: {total}",
        f"Posting date verified within 24 hours: {len(recent)}",
        f"Date not verified (check the original listing): {len(undated)}",
        "Target: Hyderabad / India-eligible Remote | Experience: about 4 years | Salary goal: 15–20 LPA",
        "Ranking: .NET/C# relevance, role-title match, location, skill overlap and recency.",
        "Salary is not used as a hard filter because many employers do not disclose it.",
        "",
        "SOURCE HEALTH"
    ]
    for name, status in statuses.items():
        lines.append(f"- {name}: {status}")

    if recent:
        lines += ["", "RECENT MATCHES — ORIGINAL POSTING DATE WITHIN THE LAST 24 HOURS", ""]
        for i, job in enumerate(recent, 1):
            lines += [
                f"{i}. [{job['score']}/100] {job['title']} — {job['company']}",
                f"   Location: {job['location']} | Source: {job['source']}",
                f"   Posted: {job['posted_label']} | Salary: {job['salary']}",
                f"   Skills matched: {job['skills']}",
                f"   Apply / details: {job['url']}",
                ""
            ]

    if undated:
        lines += [
            "", "ADDITIONAL LEADS — POSTING DATE COULD NOT BE VERIFIED",
            "These may be useful, but open the original page and confirm the job is still active and newly posted.",
            ""
        ]
        for i, job in enumerate(undated, 1):
            lines += [
                f"{i}. [{job['score']}/100] {job['title']} — {job['company']}",
                f"   Location: {job['location']} | Source: {job['source']}",
                f"   Date: {job['posted_label']} | Salary: {job['salary']}",
                f"   Skills matched: {job['skills']}",
                f"   Apply / details: {job['url']}",
                ""
            ]

    lines += ["", "LIVE PORTAL SEARCHES — OPEN THESE TO CHECK THE LATEST VACANCIES", ""]
    for label, url in search_links():
        lines.append(f"- {label}: {url}")

    lines += [
        "", "IMPORTANT",
        "- This bot aggregates public feeds, official/public ATS endpoints and web-search results; it does not have privileged access to every job board.",
        "- LinkedIn and Indeed are linked to live searches rather than scraped or logged into. Do not provide portal passwords to this workflow.",
        "- Search-engine freshness is not proof of the employer's posting date. Verify the date, location eligibility, experience requirement and salary on the original listing.",
        "- Never pay a recruiter or share OTPs, banking details or identity documents before verifying the employer."
    ]
    msg.set_content("\n".join(lines))

    with smtplib.SMTP_SSL(
        os.getenv("SMTP_HOST", "smtp.gmail.com"),
        int(os.getenv("SMTP_PORT", "465"))
    ) as smtp:
        smtp.login(sender, password)
        smtp.send_message(msg)

    print(f"Sent job digest to {recipient}; {len(recent)} dated + {len(undated)} undated matches.")
    print("Source health: " + " | ".join(f"{k}: {v}" for k, v in statuses.items()))


if __name__ == "__main__":
    main()
