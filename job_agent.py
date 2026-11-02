#!/usr/bin/env python3
"""
Job-application cold-email agent.

Pipeline:  collect jobs  ->  extract recruiter email + job ID  ->  the AI scores fit
           against your resume and writes a tailored email  ->  save drafts (default)
           or send with your resume attached (--send, rate-limited, de-duplicated).

Job sources:
  * a folder of JD files (.pdf / .txt) - e.g. JDs saved from LinkedIn, Naukri, emails, PDFs
  * Greenhouse and Lever public job-board APIs (legal, no scraping needed)

AI provider: free Groq by default (set LLM_PROVIDER=gemini or claude to switch).
"""
import argparse
import csv
import hashlib
import html
import json
import os
import re
import smtplib
import time
from email.message import EmailMessage
from pathlib import Path

import requests
from dotenv import load_dotenv
from pypdf import PdfReader

load_dotenv()
# Which AI writes the emails. "groq" and "gemini" have free tiers; "claude" is paid.
PROVIDER = os.getenv("LLM_PROVIDER", "groq").lower()
PROVIDERS = {
    "groq": ("https://api.groq.com/openai/v1/chat/completions", "GROQ_API_KEY", "openai/gpt-oss-120b"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "GEMINI_API_KEY", "gemini-2.5-flash"),
    "claude": (None, "ANTHROPIC_API_KEY", "claude-sonnet-5-5"),
}
MODEL = os.getenv("LLM_MODEL") or PROVIDERS[PROVIDER][2]
CALL_GAP = int(os.getenv("CALL_GAP_SECONDS", "20"))  # pause between AI calls to stay inside free limits
OUT = Path("out")
LOG = OUT / "sent_log.csv"  # committed back to the repo by the workflow

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
JOBID_RE = re.compile(
    r"(?:job\s*(?:id|code|ref(?:erence)?)|req(?:uisition)?\s*(?:id|no\.?|#))\s*[:#-]?\s*([A-Z0-9][A-Z0-9-]{2,20})",
    re.I,
)
IGNORE_EMAIL_PARTS = ("noreply", "no-reply", "donotreply", "example.com", "privacy@", "unsubscribe")


# ---------------------------------------------------------------- extraction
def read_file_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        return "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
    return path.read_text(encoding="utf-8", errors="ignore")


def clean_html(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(s or ""))).strip()


def extract_emails(text: str) -> list[str]:
    found = []
    for e in EMAIL_RE.findall(text):
        e = e.strip(".").lower()
        if not any(bad in e for bad in IGNORE_EMAIL_PARTS) and e not in found:
            found.append(e)
    return found


def extract_job_id(text: str) -> str:
    m = JOBID_RE.search(text)
    return m.group(1) if m else ""


def make_job(source, company, title, url, text) -> dict:
    return {
        "key": hashlib.sha1((url or text[:500]).encode()).hexdigest()[:12],
        "source": source,
        "company": company,
        "title": title,
        "url": url,
        "text": text[:12000],
        "emails": extract_emails(text),
        "job_id": extract_job_id(text),
    }


# ---------------------------------------------------------------- sources
def jobs_from_folder(folder: str) -> list[dict]:
    jobs = []
    for p in sorted(Path(folder).glob("*")):
        if p.suffix.lower() in (".pdf", ".txt", ".md"):
            jobs.append(make_job("file", "", p.stem, str(p), read_file_text(p)))
    return jobs


def jobs_from_greenhouse(slug: str) -> list[dict]:
    r = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true", timeout=30)
    r.raise_for_status()
    return [
        make_job("greenhouse", slug, j["title"], j["absolute_url"],
                 f'{j["title"]}\nLocation: {j.get("location", {}).get("name", "")}\n{clean_html(j.get("content", ""))}')
        for j in r.json().get("jobs", [])
    ]


def jobs_from_lever(slug: str) -> list[dict]:
    r = requests.get(f"https://api.lever.co/v0/postings/{slug}?mode=json", timeout=30)
    r.raise_for_status()
    return [
        make_job("lever", slug, j["text"], j["hostedUrl"],
                 f'{j["text"]}\nLocation: {j.get("categories", {}).get("location", "")}\n{j.get("descriptionPlain", "")}')
        for j in r.json()
    ]


# ---------------------------------------------------------------- AI step
PROMPT = """You are helping a job seeker apply. Compare the RESUME to the JOB DESCRIPTION.

Return ONLY a JSON object with keys:
  company, role, job_id (from the JD if present, else ""),
  fit_score (0-100, be strict: core skills + years + location),
  top_matches (list of 3 short strings: concrete resume facts that match the JD),
  gaps (list of short strings),
  subject (email subject; include role and job ID if known),
  body (cold email, max 150 words, plain text).

Rules for the email:
- Address it to "{greeting}". Sign off as {name}.
- Use ONLY facts that appear in the resume. Never invent experience, numbers or skills.
- Open with the specific role (and job ID), give 2-3 quantified matches, one line on why this company.
- End with a low-friction ask (a 10-minute call or forwarding to the hiring manager) and note the resume is attached.
- No placeholders like [Company]. No flattery, no emojis.

RESUME:
{resume}

JOB DESCRIPTION (source: {source}, url: {url}):
{jd}
"""


def ask_llm(prompt: str) -> str:
    url, key_name, _ = PROVIDERS[PROVIDER]
    key = os.environ.get(key_name)
    if not key:
        raise SystemExit(f"Missing {key_name}. Add it as a secret / in .env.")
    if PROVIDER == "claude":
        import anthropic
        msg = anthropic.Anthropic(api_key=key).messages.create(
            model=MODEL, max_tokens=1200, messages=[{"role": "user", "content": prompt}])
        return msg.content[0].text
    for attempt in range(5):
        r = requests.post(url, timeout=120, headers={"Authorization": f"Bearer {key}"}, json={
            "model": MODEL, "max_tokens": 1500, "temperature": 0.4,
            "messages": [{"role": "user", "content": prompt}]})
        if r.status_code == 429:  # free-tier rate limit: wait and retry
            wait = int(float(r.headers.get("retry-after", 30))) + 5
            print(f"    rate limited, waiting {wait}s")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    raise RuntimeError("still rate limited after 5 tries")


def analyse(resume: str, job: dict, name: str) -> dict:
    greeting = "Hi " + job["emails"][0].split("@")[0].split(".")[0].title() if job["emails"] else "Hi"
    raw = ask_llm(PROMPT.format(
        greeting=greeting, name=name, resume=resume[:8000],
        source=job["source"], url=job["url"], jd=job["text"][:6000]))
    time.sleep(CALL_GAP)
    return json.loads(raw[raw.find("{"): raw.rfind("}") + 1])


# ---------------------------------------------------------------- sending
def send_email(to: str, subject: str, body: str, resume_path: str):
    m = EmailMessage()
    m["From"] = os.environ["SMTP_USER"]
    m["To"] = to
    m["Subject"] = subject
    m.set_content(body)
    m.add_attachment(Path(resume_path).read_bytes(), maintype="application",
                     subtype="pdf", filename=Path(resume_path).name)
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    with smtplib.SMTP_SSL(host, int(os.getenv("SMTP_PORT", "465"))) as s:
        s.login(os.environ["SMTP_USER"], os.environ["SMTP_APP_PASSWORD"])
        s.send_message(m)


def load_log() -> tuple[dict, set]:
    """Return {job_key: latest status} and the set of addresses already emailed."""
    if not LOG.exists():
        return {}, set()
    with LOG.open() as f:
        rows = list(csv.DictReader(f))
    status = {r["key"]: r["status"] for r in rows}
    return status, {r["to"] for r in rows if r["status"] == "sent" and r["to"]}


def append_log(row: dict):
    new = not LOG.exists()
    with LOG.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["key", "to", "company", "role", "job_id", "score", "status", "url"])
        if new:
            w.writeheader()
        w.writerow(row)


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="AI cold-email job application agent")
    ap.add_argument("--resume", required=True, help="your resume PDF")
    ap.add_argument("--name", required=True, help="your full name for the sign-off")
    ap.add_argument("--jd-dir", help="folder of JD PDFs/text files")
    ap.add_argument("--greenhouse", nargs="*", default=[], help="Greenhouse board slugs, e.g. razorpay")
    ap.add_argument("--lever", nargs="*", default=[], help="Lever company slugs")
    ap.add_argument("--keywords", nargs="*", default=[], help="only keep API jobs whose title has one of these")
    ap.add_argument("--min-score", type=int, default=70)
    ap.add_argument("--send", action="store_true", help="actually send (default: drafts only)")
    ap.add_argument("--max-send", type=int, default=10, help="max emails per run")
    ap.add_argument("--delay", type=int, default=120, help="seconds between sends")
    ap.add_argument("--max-jobs", type=int, default=30, help="max new jobs to score per run (protects free AI limits)")
    a = ap.parse_args()

    OUT.mkdir(exist_ok=True)
    resume = read_file_text(Path(a.resume))
    print(f"AI: {PROVIDER} / {MODEL}")

    jobs = jobs_from_folder(a.jd_dir) if a.jd_dir else []
    api_jobs = []
    for s in a.greenhouse:
        api_jobs += jobs_from_greenhouse(s)
    for s in a.lever:
        api_jobs += jobs_from_lever(s)
    if a.keywords:
        kw = [k.lower() for k in a.keywords]
        api_jobs = [j for j in api_jobs if any(k in j["title"].lower() for k in kw)]
    jobs += api_jobs
    print(f"{len(jobs)} jobs collected")

    seen, emailed = load_log()
    sent = scored = 0
    drafts = []
    for job in jobs:
        to = job["emails"][0] if job["emails"] else ""
        # skip jobs already handled; 'ready' ones (good fit, not yet sent) are retried
        if seen.get(job["key"], "ready") != "ready" or (to and to in emailed):
            continue
        if scored >= a.max_jobs:
            print(f"  reached --max-jobs {a.max_jobs}; the rest wait for the next run")
            break
        scored += 1
        try:
            r = analyse(resume, job, a.name)
        except SystemExit:
            raise
        except Exception as e:
            print(f"  skip {job['title']}: {e}")
            continue
        score = int(r.get("fit_score", 0))
        print(f"  [{score:3}] {r.get('company') or job['company']} - {r.get('role') or job['title']}  {to or '(no email)'}")
        drafts.append({**job, **r, "to": to, "text": ""})

        status = "below_threshold" if score < a.min_score else ("draft" if not to else "ready")
        if status == "ready" and a.send and sent < a.max_send:
            send_email(to, r["subject"], r["body"], a.resume)
            status, sent = "sent", sent + 1
            time.sleep(a.delay)
        # every analysed job is logged so later runs don't re-score it or email anyone twice
        append_log({"key": job["key"], "to": to, "company": r.get("company"), "role": r.get("role"),
                    "job_id": r.get("job_id") or job["job_id"], "score": score, "status": status,
                    "url": job["url"]})

    with (OUT / "drafts.csv").open("w", newline="") as f:
        cols = ["fit_score", "company", "role", "job_id", "to", "subject", "body", "top_matches", "gaps", "url"]
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for d in sorted(drafts, key=lambda d: -int(d.get("fit_score", 0))):
            w.writerow({**d, "top_matches": "; ".join(d.get("top_matches", [])), "gaps": "; ".join(d.get("gaps", []))})
    print(f"Done. {len(drafts)} drafts -> out/drafts.csv, {sent} emails sent.")


if __name__ == "__main__":
    main()
