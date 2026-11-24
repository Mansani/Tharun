# Daily .NET / C# / Azure Job Radar

A personal daily job discovery workflow for Tharun's profile. It runs at **8:00 PM Asia/Kolkata** and emails ranked openings for Hyderabad and India-eligible remote roles.

## What it searches

### Direct feeds and public endpoints (no extra API key)
- Remote OK public job feed
- Arbeitnow public job-board API
- Jobicy remote jobs API
- We Work Remotely public programming RSS feed (credited and linked to the original listing)

### Employer career pages (configure company board IDs)
- Greenhouse public boards
- Lever public postings
- Ashby public job boards
- SmartRecruiters public company postings

### Optional job-search APIs
- Adzuna India API
- Jooble India REST API
- Brave Search API for freshness-filtered discovery across indexed job sites, including results from major portals

### Portal searches included in every email
- LinkedIn Hyderabad / India-remote filters
- Naukri Hyderabad
- Indeed Hyderabad, last 24 hours
- Google Jobs / Google web search
- Foundit, Hirist, Cutshort and Instahyre
- Employer career-site search

The workflow does **not** log in to portals or bypass CAPTCHAs, paywalls, robots rules or anti-bot controls. LinkedIn, Indeed and Naukri are provided as live search links and may also appear in the optional web-search results when indexed. Search indexing is not equivalent to a guaranteed live posting.

## Email ranking and freshness

The digest:
- Prioritizes C#, .NET, ASP.NET Core, Web API, EF Core, SQL Server and Azure backend work.
- Matches Tharun's actual skills and profile; it does not claim hands-on Docker, Kubernetes or Redis.
- Prioritizes Hyderabad and India-eligible remote work.
- Separates roles with a verified posting timestamp in the last 24 hours from undated/search-indexed leads.
- Shows source health so failed or unconfigured connectors are visible.
- De-duplicates identical job URLs and links to the original employer / job-board posting.

The 15–20 LPA target is shown as guidance, not a hard exclusion, because many listings do not publish salary. Verify experience, location eligibility, compensation and whether the vacancy is still open on the original listing.

## Required GitHub secrets

In **Settings → Secrets and variables → Actions → Repository secrets**, add:

| Secret | Purpose |
|---|---|
| `SMTP_USER` | Gmail sender address |
| `SMTP_APP_PASSWORD` | Gmail App Password (not your normal Gmail password) |
| `JOB_ALERT_TO` | Recipient email address |

Optional API secrets:

| Secret | Purpose |
|---|---|
| `ADZUNA_APP_ID` | Adzuna API application ID |
| `ADZUNA_APP_KEY` | Adzuna API application key |
| `JOOBLE_API_KEY` | Jooble API key issued for India |
| `BRAVE_SEARCH_API_KEY` | Brave Search API subscription token |

## Optional GitHub Actions variables

In **Settings → Secrets and variables → Actions → Variables**, set:

| Variable | Format / purpose |
|---|---|
| `GREENHOUSE` | Space-separated Greenhouse board slugs |
| `LEVER` | Space-separated Lever company slugs |
| `ASHBY` | Space-separated Ashby job-board names |
| `SMARTRECRUITERS` | Space-separated SmartRecruiters company identifiers |
| `JOOBLE_API_BASE_URL` | Defaults to `https://in.jooble.org/api`; use the country-specific API base matching your key |

Only configure company-board identifiers for employers you actually want to monitor. The optional API connectors report as “Not configured” until their credentials or company IDs are supplied.

## Run manually

1. Open the repository's **Actions** tab.
2. Select **Daily 8 PM job email**.
3. Click **Run workflow** and select `main`.
4. Review the run log and the **SOURCE HEALTH** section in the email.

Scheduled run: `30 14 * * *` UTC = **8:00 PM IST**.

## Profile

- Hyderabad, India; around 4 years of professional experience plus internship experience.
- Target roles: .NET Developer, C# Developer, ASP.NET Core Developer, Backend Engineer (.NET), Software Engineer and Azure/.NET roles.
- Target compensation: 15–20 LPA.
- Skills and resume facts are maintained in `profile.json`.

The existing cold-email agent and the separate morning job-assistant workflow are preserved.
