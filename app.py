import uuid
from flask import Flask, request, jsonify, send_from_directory
import agent
app = Flask(__name__, static_folder="static")

def sess(): return agent.SESSIONS.setdefault(request.headers.get("X-Session", "default"), {})

@app.get("/")
def index(): return send_from_directory("static", "index.html")

@app.post("/api/upload")
def upload():
    f = request.files.get("file")
    if not f: return jsonify(error="No file received."), 400
    r = agent.parse_resume(f.read(), f.filename)
    if "error" in r: return jsonify(r), 422
    s = sess(); s["resume"] = r; s["history"] = []
    return jsonify(resume=r)

@app.post("/api/chat")
def chat():
    msg = (request.json or {}).get("message", "").strip()
    if not msg: return jsonify(error="Empty message."), 400
    try: return jsonify(reply=agent.chat(sess(), msg))
    except Exception as e: return jsonify(reply=f"⚠️ Something went wrong ({type(e).__name__}). Please try again."), 200

@app.get("/api/applications")
def apps(): return jsonify(agent.load(agent.APPS_FILE, []))

if __name__ == "__main__": app.run(debug=True, port=5000)
