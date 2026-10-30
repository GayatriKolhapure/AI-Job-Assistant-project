"""Orchestrator agent + tool 'sub-agents': parse, match, apply, track."""
import io, json, os, re, threading
from datetime import datetime, timezone

BASE = os.path.dirname(__file__)
JOBS_FILE = os.path.join(BASE, "jobs.json")
APPS_FILE = os.path.join(BASE, "applications.json")
LOCK = threading.Lock()
SESSIONS = {}  # session_id -> {"resume":..., "last":[ids], "history":[...]}

SKILLS = ["python","javascript","typescript","react","node.js","next.js","vue","angular","java","c++","c#","go",
 "rust","ruby","php","sql","postgresql","mysql","mongodb","redis","aws","azure","gcp","docker","kubernetes",
 "git","flask","django","fastapi","spring","html","css","tailwind","graphql","rest","machine learning",
 "deep learning","pytorch","tensorflow","nlp","llm","langchain","pandas","numpy","kafka","terraform",
 "linux","ci/cd","swift","kotlin","flutter","android","ios","figma","tableau","excel","spark"]
TITLES = ["software engineer","software developer","frontend developer","backend developer","full stack developer",
 "data scientist","data analyst","machine learning engineer","devops engineer","mobile developer",
 "qa engineer","product manager","ui/ux designer","data engineer","ai engineer","web developer"]

def load(path, default):
    try:
        with open(path) as f: return json.load(f)
    except Exception: return default

def find_skills(text):
    t = text.lower()
    return [s for s in SKILLS if re.search(r"(?<![a-z+#])" + re.escape(s) + r"(?![a-z+#])", t)]

# ---------------- Tool 1: resume parser ----------------
def parse_resume(data: bytes, filename: str):
    name = filename.lower()
    try:
        if name.endswith(".pdf"):
            from pypdf import PdfReader
            text = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages)
        elif name.endswith(".docx"):
            import docx
            text = "\n".join(p.text for p in docx.Document(io.BytesIO(data)).paragraphs)
        else:
            return {"error": "Unsupported file type. Please upload a PDF or DOCX resume."}
    except Exception as e:
        return {"error": f"Could not read this file ({type(e).__name__}). Is it corrupted or password-protected?"}
    if len(text.strip()) < 80:
        return {"error": "No readable text found (possibly a scanned image). Please upload a text-based PDF/DOCX."}
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    email = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    phone = re.search(r"(\+?\d[\d\s\-()]{8,}\d)", text)
    low = text.lower()
    desig = next((t.title() for t in TITLES if t in low), None)
    if not desig and re.search(r"developer|engineer", low): desig = "Software Engineer"
    yrs = [int(x) for x in re.findall(r"(\d{1,2})\+?\s*(?:years|yrs)", low)]
    def section(keys, stop=("experience","education","projects","skills","certifications","summary")):
        out, on = [], False
        for l in lines:
            ll = l.lower().strip(": ")
            if any(ll.startswith(k) for k in keys) and len(l) < 40: on = True; continue
            if on and ll in stop and not any(ll.startswith(k) for k in keys): break
            if on: out.append(l)
        return out[:8]
    edu = section(["education"]) or [l for l in lines if re.search(r"b\.?tech|b\.?e\b|bachelor|master|m\.?tech|mca|bca|b\.?sc", l, re.I)][:3]
    return {"name": lines[0][:60], "email": email.group(0) if email else None,
            "phone": phone.group(1).strip() if phone else None, "designation": desig,
            "skills": find_skills(text), "experience_years": max(yrs) if yrs else 0,
            "education": edu, "projects": section(["projects","project"])}

# ---------------- Tool 2: job matcher ----------------
def search_jobs(sess, remote_only=False, skills=None, location=None, keyword=None, limit=5):
    jobs = load(JOBS_FILE, [])
    if not jobs: return {"error": "Job database is empty. Run scraper.py first."}
    r = sess.get("resume") or {}
    mine = set(r.get("skills", [])); need = set(s.lower() for s in (skills or []))
    out = []
    for j in jobs:
        js = set(j["skills"])
        if remote_only and "remote" not in j["location"].lower(): continue
        if location and location.lower() not in j["location"].lower(): continue
        if need and not need <= js: continue
        if keyword and keyword.lower() not in (j["title"] + j["description"]).lower(): continue
        overlap = sorted(mine & js)
        score = 3 * len(overlap) + (5 if r.get("designation") and r["designation"].lower().split()[0] in j["title"].lower() else 0)
        if j["experience_years"] <= r.get("experience_years", 0) + 1: score += 2
        if not mine and not (need or keyword or location or remote_only): continue
        why = []
        if overlap: why.append("matching skills: " + ", ".join(overlap))
        if r.get("designation") and r["designation"].lower().split()[0] in j["title"].lower(): why.append(f"title fits {r['designation']}")
        why.append(f"needs ~{j['experience_years']} yrs (you: {r.get('experience_years',0)})")
        out.append((score, {"id": j["id"], "title": j["title"], "company": j["company"], "location": j["location"],
                            "experience_years": j["experience_years"], "skills": j["skills"][:8],
                            "link": j["source_link"], "match_reason": "; ".join(why)}))
    out.sort(key=lambda x: -x[0])
    res = [o[1] for o in out[:limit]]
    sess["last"] = [j["id"] for j in res]
    return {"jobs": res} if res else {"error": "No matching jobs. Try loosening filters (e.g. drop 'remote' or a skill)."}

# ---------------- Tool 3: applier ----------------
def apply_job(job_id):
    try: job_id = int(job_id)
    except Exception: return {"error": f"'{job_id}' is not a valid job ID."}
    job = next((j for j in load(JOBS_FILE, []) if j["id"] == job_id), None)
    if not job: return {"error": f"No job with ID {job_id} exists."}
    with LOCK:
        apps = load(APPS_FILE, [])
        if any(a["job_id"] == job_id for a in apps):
            return {"error": f"You already applied to job {job_id} ({job['title']}). No duplicate created."}
        app = {"job_id": job_id, "title": job["title"], "company": job["company"],
               "applied_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "status": "Applied"}
        apps.append(app)
        json.dump(apps, open(APPS_FILE, "w"), indent=2)
    return {"applied": app}

# ---------------- Tool 4: tracker ----------------
def list_applications():
    apps = load(APPS_FILE, [])
    return {"applications": apps} if apps else {"error": "You haven't applied to any jobs yet."}

# ---------------- Orchestrator ----------------
TOOLS = [
 {"name":"search_jobs","description":"Find/filter jobs matching the user's resume. Call again with new filters to refine.",
  "input_schema":{"type":"object","properties":{"remote_only":{"type":"boolean"},"skills":{"type":"array","items":{"type":"string"}},
  "location":{"type":"string"},"keyword":{"type":"string"},"limit":{"type":"integer"}}}},
 {"name":"apply_job","description":"Apply to a job by its job ID (the #id shown in results).",
  "input_schema":{"type":"object","properties":{"job_id":{"type":"integer"}},"required":["job_id"]}},
 {"name":"list_applications","description":"Show the user's applied jobs and statuses.","input_schema":{"type":"object","properties":{}}}]
SYSTEM = ("You are a friendly job-search assistant. Tools: search_jobs, apply_job, list_applications. "
          "If no resume is uploaded, ask the user to upload one. Always refer to jobs by their #ID. "
          "'apply to job 3' means job ID 3. Report tool errors plainly. Keep replies concise; never invent jobs.")

def run_tool(sess, name, args):
    if name == "search_jobs": return search_jobs(sess, **{k: v for k, v in args.items() if k in
                    ("remote_only","skills","location","keyword","limit")})
    if name == "apply_job": return apply_job(args.get("job_id"))
    if name == "list_applications": return list_applications()
    return {"error": "unknown tool"}

def fmt(name, res):
    if "error" in res: return "⚠️ " + res["error"]
    if "jobs" in res:
        return "Here are your matches:\n\n" + "\n\n".join(
            f"**#{j['id']} {j['title']}** — {j['company']} ({j['location']})\n_Why:_ {j['match_reason']}\n[View]({j['link']})" for j in res["jobs"]
        ) + "\n\nSay e.g. “apply to job <id>” or refine (“only remote”, “needs React”)."
    if "applied" in res: a = res["applied"]; return f"✅ Applied to **{a['title']}** at {a['company']} on {a['applied_date']}. Status: {a['status']}."
    return "Your applications:\n\n" + "\n".join(f"- #{a['job_id']} {a['title']} @ {a['company']} — {a['status']} ({a['applied_date']})" for a in res["applications"])

def rule_based(sess, msg):  # fallback when no ANTHROPIC_API_KEY
    m = msg.lower()
    if re.search(r"applied|my applications|status", m): return fmt("l", list_applications())
    a = re.search(r"apply.*?(\d+)", m)
    if a: return fmt("a", apply_job(a.group(1)))
    args = {"remote_only": "remote" in m}
    sk = [s for s in SKILLS if re.search(r"(?<![a-z+#])" + re.escape(s) + r"(?![a-z+#])", m)]
    if sk: args["skills"] = sk
    if re.search(r"job|role|show|find|recommend|need|only", m) or sk or args["remote_only"]:
        if not sess.get("resume") and not sk and not args["remote_only"]:
            return "Please upload your resume first (📎 button) so I can match jobs."
        return fmt("s", search_jobs(sess, **args))
    return "I can recommend jobs, refine them (“only remote”), apply (“apply to job 12”), or show your applications."

def chat(sess, msg):
    if not os.getenv("ANTHROPIC_API_KEY"): return rule_based(sess, msg)
    import anthropic
    client = anthropic.Anthropic()
    ctx = SYSTEM + "\nResume: " + (json.dumps({k: sess["resume"][k] for k in ("designation","skills","experience_years")})
                                   if sess.get("resume") else "NOT UPLOADED")
    h = sess.setdefault("history", []); h.append({"role": "user", "content": msg})
    for _ in range(5):
        r = client.messages.create(model=os.getenv("MODEL", "claude-sonnet-4-5"), max_tokens=1000, system=ctx, tools=TOOLS, messages=h[-20:])
        h.append({"role": "assistant", "content": r.content})
        if r.stop_reason != "tool_use":
            return "".join(b.text for b in r.content if b.type == "text")
        results = [{"type": "tool_result", "tool_use_id": b.id, "content": json.dumps(run_tool(sess, b.name, b.input))}
                   for b in r.content if b.type == "tool_use"]
        h.append({"role": "user", "content": results})
    return "Sorry, I couldn't complete that. Please rephrase."
