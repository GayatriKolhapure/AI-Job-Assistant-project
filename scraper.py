"""Scrapes real jobs from public job APIs (Remotive, Arbeitnow, RemoteOK) -> jobs.json. Run: python scraper.py"""
import json, re, requests, html
from agent import find_skills
H = {"User-Agent": "Mozilla/5.0 job-assistant-assessment"}
def clean(s): return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()
def exp(title, desc):
    m = re.search(r"(\d{1,2})\+?\s*(?:years|yrs)", desc.lower())
    if m: return min(int(m.group(1)), 15)
    t = title.lower()
    return 5 if re.search(r"senior|sr\.|lead|staff|principal", t) else 0 if re.search(r"intern|junior|jr|graduate", t) else 2
def get(url, **kw):
    try: return requests.get(url, headers=H, timeout=30, **kw).json()
    except Exception as e: print("failed", url, e); return None
jobs = []
def add(title, company, loc, desc, link, src):
    desc = clean(desc)[:1500]
    jobs.append({"title": title, "company": company, "location": loc or "Remote", "experience_years": exp(title, desc),
                 "skills": find_skills(title + " " + desc), "description": desc, "source_link": link, "source": src})
d = get("https://remotive.com/api/remote-jobs")
for j in (d or {}).get("jobs", []): add(j["title"], j["company_name"], "Remote - " + (j.get("candidate_required_location") or ""), j["description"], j["url"], "remotive")
for p in range(1, 21):
    d = get(f"https://www.arbeitnow.com/api/job-board-api?page={p}")
    if not d or not d.get("data"): break
    for j in d["data"]: add(j["title"], j["company_name"], ("Remote - " if j.get("remote") else "") + j.get("location", ""), j["description"], j["url"], "arbeitnow")
d = get("https://remoteok.com/api")
for j in (d or [])[1:]: add(j.get("position", ""), j.get("company", ""), "Remote - " + (j.get("location") or "Worldwide"), j.get("description", ""), j.get("url", ""), "remoteok")
seen, out = set(), []
for j in jobs:
    k = j["source_link"]
    if k and k not in seen and j["title"]: seen.add(k); out.append(j)
for i, j in enumerate(out[:2000], 1): j["id"] = i
json.dump(out[:2000], open("jobs.json", "w"), indent=1)
print(f"Saved {len(out[:2000])} jobs to jobs.json")
