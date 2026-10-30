# AI Job Chat Assistant (Hidani Tech assessment)
Chat assistant: upload resume → parsed details → job recommendations with match reasons → refine in chat → apply → track.

## Setup
```
pip install -r requirements.txt
python scraper.py          # builds jobs.json (1,500-2,000 real listings)
export ANTHROPIC_API_KEY=sk-...   # optional; without it a rule-based router is used
python app.py              # http://localhost:5000
```
## Architecture
`Orchestrator (agent.chat)` — Claude with tool calling (fallback: regex intent router) delegates to tools/sub-agents:
- `parse_resume` – PDF/DOCX text extraction + heuristic field extraction
- `search_jobs` – scoring on skill overlap, title fit, experience; filters (remote, skills, location, keyword); gives `match_reason`
- `apply_job` – validates ID, dedupes, writes `applications.json` (job_id, applied_date, status)
- `list_applications` – tracking

## Dataflow
Upload → `/api/upload` → parser → session memory (resume) → `/api/chat` → orchestrator → tool → JSON DB → reply.
Session state is keyed by an `X-Session` header (no auth). Errors handled: unreadable/scanned resume, unsupported type, empty results, invalid/duplicate job ID.

## APIs used
Remotive, Arbeitnow, RemoteOK public job APIs (scraping); Anthropic Messages API (orchestration).

## Deploy (Render)
New Web Service → connect repo → build `pip install -r requirements.txt` → start `gunicorn app:app` → env `ANTHROPIC_API_KEY`.
Commit `jobs.json`. Note: free-tier disks are ephemeral, so `applications.json` resets on redeploy.
