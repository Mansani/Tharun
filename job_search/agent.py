import csv, json, os, re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
import requests

ROOT=Path(__file__).resolve().parent
PROFILE=json.loads((ROOT/"profile.json").read_text(encoding="utf-8"))
OUT=ROOT.parent/"out"; OUT.mkdir(exist_ok=True)
SKILLS=[s.lower() for g in PROFILE["skills"].values() for s in g]
TARGETS=[s.lower() for s in PROFILE["target_roles"]]
LOCATIONS=[s.lower() for s in PROFILE["locations"]]

def clean(x): return re.sub(r"\\s+"," ",re.sub(r"<[^>]+>"," ",x or "")).strip()

def greenhouse(slug):
    r=requests.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",timeout=30); r.raise_for_status()
    return [{"source":"Greenhouse","company":slug,"title":j.get("title",""),"location":j.get("location",{}).get("name",""),"url":j.get("absolute_url",""),"description":clean(j.get("content",""))} for j in r.json().get("jobs",[])]

def lever(slug):
    r=requests.get(f"https://api.lever.co/v0/postings/{slug}?mode=json",timeout=30); r.raise_for_status()
    return [{"source":"Lever","company":slug,"title":j.get("text",""),"location":j.get("categories",{}).get("location",""),"url":j.get("hostedUrl",""),"description":clean(j.get("descriptionPlain",""))} for j in r.json()]

def score(j):
    text=(j["title"]+" "+j["description"]).lower()
    title=sum(1 for t in TARGETS if t in j["title"].lower())
    hits=sorted({s for s in SKILLS if s in text})
    loc=j["location"].lower()
    location=any(x in loc for x in LOCATIONS) or "remote" in loc
    s=min(100,title*10+min(55,len(hits)*5)+(15 if location else 0))
    if j["location"] and not location: s-=15
    return max(0,s),hits,location

def li_url(title,location):
    return "https://www.linkedin.com/jobs/search/?keywords="+quote(title)+"&location="+quote(location)+"&f_TPR=r86400"

def main():
    jobs=[]
    for slug in os.getenv("GREENHOUSE","").split():
        try: jobs += greenhouse(slug)
        except Exception as e: print("Greenhouse",slug,e)
    for slug in os.getenv("LEVER","").split():
        try: jobs += lever(slug)
        except Exception as e: print("Lever",slug,e)

    rows=[]
    for j in jobs:
        s,hits,_=score(j)
        if s < int(os.getenv("MIN_SCORE","60")): continue
        rows.append({
            "score":s,"company":j["company"],"title":j["title"],"location":j["location"],
            "source":j["source"],"matched_skills":", ".join(hits[:12]),"url":j["url"],
            "linkedin_24h_hyderabad":li_url(j["title"],"Hyderabad"),
            "linkedin_24h_remote":li_url(j["title"],"Remote"),
            "description":j["description"][:5000]
        })
    rows.sort(key=lambda x:-x["score"])
    cols=["score","company","title","location","source","matched_skills","url","linkedin_24h_hyderabad","linkedin_24h_remote","description"]
    with (OUT/"matched_jobs.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=cols); w.writeheader(); w.writerows(rows)
    with (OUT/"daily_report.md").open("w",encoding="utf-8") as f:
        f.write("# Daily .NET/Azure Job Report\\n\\n")
        f.write(f"Generated: {datetime.now(timezone.utc).isoformat()}\\n\\n")
        f.write(f"Matched jobs: **{len(rows)}**\\n\\n")
        for r in rows[:30]:
            f.write(f"## {r['score']}/100 — {r['title']} — {r['company']}\\n")
            f.write(f"- Location: {r['location']}\\n- Matching skills: {r['matched_skills']}\\n- Apply: {r['url']}\\n- LinkedIn Hyderabad (24h): {r['linkedin_24h_hyderabad']}\\n- LinkedIn Remote (24h): {r['linkedin_24h_remote']}\\n\\n")
if __name__=="__main__": main()
