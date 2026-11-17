import os, re, smtplib, html
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from urllib.parse import quote
import requests

NOW=datetime.now(timezone.utc)
CUTOFF=NOW-timedelta(hours=24)
TERMS=[".net","dotnet","c#","c sharp","asp.net","asp.net core","azure","backend engineer","software engineer"]
LOCATIONS=["hyderabad","remote","india"]
SKILLS=["c#",".net","asp.net core","web api","ef core","sql server","azure functions","azure app service","azure","jwt","rbac","nunit","in-memory caching","polly","blob storage"]
S=requests.Session()
S.headers.update({"User-Agent":"TharunDailyJobDigest/1.0 (personal job search; contact: configured mailbox)"})

def parse_date(value):
    if not value: return None
    try:
        if isinstance(value,(int,float)):
            return datetime.fromtimestamp(value/1000 if value>10**12 else value,tz=timezone.utc)
        d=datetime.fromisoformat(str(value).replace("Z","+00:00"))
        return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
    except Exception: return None

def add(rows,source,title,company,location,url,description,date):
    if not title or not url: return
    dt=parse_date(date)
    if dt and dt<CUTOFF: return
    text=(title+" "+description).lower()
    if not any(t in text for t in TERMS): return
    loc=(location or "").lower()
    if loc and not any(x in loc for x in LOCATIONS): return
    hits=sorted({x for x in SKILLS if x in text})
    score=min(100, min(55,len(hits)*7)+25+ (20 if "hyderabad" in loc or "remote" in loc else 0))
    rows.append({"score":score,"source":source,"title":title,"company":company or "Not specified",
                 "location":location or "Not specified","url":url,"date":dt.isoformat() if dt else "Date not provided",
                 "skills":", ".join(hits[:10]),"description":re.sub(r"\\s+"," ",description)[:500]})

def fetch_json(url):
    r=S.get(url,timeout=35); r.raise_for_status(); return r.json()

def collect():
    rows=[]
    # RemoteOK public feed. Respect source attribution and link to canonical listing.
    try:
        data=fetch_json("https://remoteok.com/api")
        for j in data:
            if not isinstance(j,dict) or not j.get("position"): continue
            add(rows,"Remote OK",j.get("position"),j.get("company"),j.get("location"),
                j.get("url") or j.get("apply_url"),j.get("description",""),
                j.get("date") or j.get("epoch"))
    except Exception as e: print("Remote OK feed:",e)

    # Arbeitnow public job-board API.
    try:
        data=fetch_json("https://www.arbeitnow.com/api/job-board-api")
        for j in data.get("data",[]):
            add(rows,"Arbeitnow",j.get("title"),j.get("company_name"),j.get("location"),
                j.get("url"),j.get("description",""),j.get("created_at"))
    except Exception as e: print("Arbeitnow feed:",e)

    # Jobicy remote job feed.
    try:
        data=fetch_json("https://jobicy.com/api/v2/remote-jobs?count=50")
        for j in data.get("jobs",[]):
            add(rows,"Jobicy",j.get("jobTitle"),j.get("companyName"),j.get("jobGeo"),
                j.get("url"),j.get("jobDescription",""),j.get("pubDate"))
    except Exception as e: print("Jobicy feed:",e)

    # Company career sites with public ATS APIs. Supply known board/company slugs as GitHub variables.
    for slug in os.getenv("GREENHOUSE","").split():
        try:
            data=fetch_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")
            for j in data.get("jobs",[]):
                add(rows,"Greenhouse",j.get("title"),slug,j.get("location",{}).get("name"),
                    j.get("absolute_url"),j.get("content",""),j.get("updated_at"))
        except Exception as e: print("Greenhouse",slug,e)
    for slug in os.getenv("LEVER","").split():
        try:
            data=fetch_json(f"https://api.lever.co/v0/postings/{slug}?mode=json")
            for j in data:
                c=j.get("categories",{})
                add(rows,"Lever",j.get("text"),slug,c.get("location") or ", ".join(c.get("allLocations",[])),
                    j.get("hostedUrl"),j.get("descriptionPlain",""),j.get("createdAt"))
        except Exception as e: print("Lever",slug,e)

    # Remove duplicates by canonical URL and sort highest match first.
    unique={}
    for j in rows: unique[j["url"]]=j
    return sorted(unique.values(),key=lambda x:(-x["score"],x["title"].lower()))[:40]

def main():
    jobs=collect()
    recipient=os.environ.get("JOB_ALERT_TO") or os.environ.get("SMTP_USER")
    sender=os.environ.get("SMTP_USER")
    password=os.environ.get("SMTP_APP_PASSWORD")
    if not recipient or not sender or not password:
        raise SystemExit("Missing JOB_ALERT_TO (optional), SMTP_USER, or SMTP_APP_PASSWORD GitHub secret.")
    msg=EmailMessage()
    msg["Subject"]=f"Daily .NET/Azure job matches — {NOW.astimezone(timezone(timedelta(hours=5,minutes=30))).strftime('%d %b %Y')} ({len(jobs)} matches)"
    msg["From"]=sender; msg["To"]=recipient
    if not jobs:
        body="No matching jobs with a verifiable last-24-hour posting date were found today. Search again tomorrow. LinkedIn search (last 24 hours): https://www.linkedin.com/jobs/search/?keywords=.NET%20C%23%20Azure&location=Hyderabad&f_TPR=r86400"
    else:
        parts=[f"Daily .NET / C# / Azure job digest — {len(jobs)} matches found.", "Profile: ~4 years, Hyderabad / Remote, target 15–20 LPA.", "Jobs with unknown posting dates may appear; check each listing before applying.", ""]
        for i,j in enumerate(jobs,1):
            parts += [f"{i}. [{j['score']}/100] {j['title']} — {j['company']}",
                      f"   Location: {j['location']} | Source: {j['source']} | Posted: {j['date']}",
                      f"   Matching skills: {j['skills']}",f"   Apply: {j['url']}",""]
        parts += ["LinkedIn — Hyderabad, posted in last 24 hours:",
                  "https://www.linkedin.com/jobs/search/?keywords=.NET%20C%23%20Azure&location=Hyderabad&f_TPR=r86400",
                  "LinkedIn — Remote, posted in last 24 hours:",
                  "https://www.linkedin.com/jobs/search/?keywords=.NET%20C%23%20Azure&location=Remote&f_TPR=r86400"]
        body="\\n".join(parts)
    msg.set_content(body)
    with smtplib.SMTP_SSL(os.getenv("SMTP_HOST","smtp.gmail.com"),int(os.getenv("SMTP_PORT","465"))) as smtp:
        smtp.login(sender,password); smtp.send_message(msg)
    print(f"Sent digest to {recipient}; {len(jobs)} matching listings.")

if __name__=="__main__": main()
