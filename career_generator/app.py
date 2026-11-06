import json
import os
import sqlite3
import time

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

load_dotenv()
app = Flask(__name__)

API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
DB = "careers.db"
DOCS = ["summary", "skill_gap", "learning", "interview"]
REQUIRED = ["name", "education_level", "current_skills", "interests",
            "target_role", "strengths", "experience_level"]


# ---------- database (SQLite, built into Python) ----------
def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


with db() as con:
    con.execute("""CREATE TABLE IF NOT EXISTS profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT,
        created TEXT DEFAULT CURRENT_TIMESTAMP, data TEXT)""")


# ---------- LLM call ----------
def ask_llm(prompt, as_json=False):
    key = os.getenv("GROQ_API_KEY")
    if not key or key == "paste_your_key_here":
        raise RuntimeError("Add your Groq API key to the .env file.")
    body = {"model": MODEL, "temperature": 0.5,
            "messages": [{"role": "user", "content": prompt}]}
    if as_json:
        body["response_format"] = {"type": "json_object"}
    for _ in range(3):  # if rate-limited, wait and try again
        res = requests.post(API_URL, headers={"Authorization": f"Bearer {key}"},
                            json=body, timeout=60)
        if res.status_code != 429:
            break
        try:
            wait = float(res.headers.get("retry-after", 10))
        except ValueError:
            wait = 10
        time.sleep(min(wait, 20))
    if res.status_code == 429:
        raise RuntimeError("Groq rate limit reached. Wait a minute and try again.")
    res.raise_for_status()
    return res.json()["choices"][0]["message"]["content"]


# ---------- input validation ----------
def check_form(f):
    for key, label in [("name", "Name"), ("skills", "Skills"),
                       ("interests", "Academic interests"), ("goal", "Career goal")]:
        v = (f.get(key) or "").strip()
        if len(v) < 2:
            return f"{label} is too short."
        if len(v) > 500:
            return f"{label} is too long (500 characters max)."
    return None


# ---------- step 1: master profile (with retry + key check) ----------
def build_profile(form):
    prompt = f"""You are a career counsellor. Return ONLY a JSON object with these keys:
"name", "education_level", "current_skills" (list), "interests" (list),
"target_role" (string), "strengths" (list of 3), "experience_level" (beginner, intermediate or advanced).
Do not invent skills the student did not mention.

Name: {form['name']}
Education: {form.get('education', 'Undergraduate')}
Skills: {form['skills']}
Academic interests: {form['interests']}
Career goal: {form['goal']}"""
    for _ in range(2):  # try twice
        try:
            profile = json.loads(ask_llm(prompt, as_json=True))
            if all(k in profile for k in REQUIRED):
                return profile
        except json.JSONDecodeError:
            pass
    raise RuntimeError("The AI returned an unusable profile twice. Please try again.")


# ---------- step 2: four documents, all from the SAME profile ----------
def make_prompts(profile):
    base = ("Use ONLY this student profile as the source of truth. Do not contradict it.\n\nPROFILE:\n"
            + json.dumps(profile, indent=2) + "\n\n")
    return {
        "summary": base + "Write a professional summary of about 100 words in first person, suitable for a LinkedIn About section. Return plain text.",
        "skill_gap": base + "Write a skill-gap report in Markdown with three sections: '## Skills you have', '## Skills the role needs', '## Missing skills'. Under Missing skills, give each gap a priority (High, Medium or Low) and one line explaining why.",
        "learning": base + "Write a learning plan in Markdown with: '## Free courses' (4 items with platform), '## Projects to build' (3 items), and '## 12-week timeline' (grouped by 4-week blocks). Every item must close one of the student's missing skills.",
        "interview": base + "Write interview prep in Markdown: 6 likely interview questions for the target role (mix technical and behavioural), each with a short sample answer that uses the student's actual skills.",
    }


def generate_all(profile):
    prompts = make_prompts(profile)
    # one at a time, so we stay under the free-tier rate limit
    return {k: ask_llm(p) for k, p in prompts.items()}


# ---------- step 3: consistency check ----------
def check_consistency(profile, docs):
    text = "\n\n".join(f"=== {k.upper()} ===\n{docs[k]}" for k in DOCS)
    prompt = ("You are a strict reviewer. Compare these four documents against the student profile. "
              "Look for contradictions in: name, skills, target role, experience level, and skills "
              "claimed that the student does not have. Reply in Markdown: start with '## Verdict' "
              "(Consistent or Issues found), then list each issue with the document it appears in "
              "and a suggested fix. If none, say so.\n\nPROFILE:\n"
              + json.dumps(profile) + "\n\n" + text)
    return ask_llm(prompt)


# ---------- routes ----------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/profile", methods=["POST"])
def profile():
    form = request.get_json() or {}
    err = check_form(form)
    if err:
        return jsonify({"error": err}), 400
    try:
        return jsonify(build_profile({k: str(v).strip() for k, v in form.items()}))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/generate", methods=["POST"])
def generate():
    profile = (request.get_json() or {}).get("profile")
    if not profile or not all(k in profile for k in REQUIRED):
        return jsonify({"error": "Profile is incomplete."}), 400
    try:
        docs = generate_all(profile)
        docs["consistency"] = check_consistency(profile, docs)
        with db() as con:
            cur = con.execute("INSERT INTO profiles (name, data) VALUES (?, ?)",
                              (profile["name"], json.dumps({"profile": profile, **docs})))
            pid = cur.lastrowid
        return jsonify({"id": pid, "profile": profile, **docs})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/regenerate", methods=["POST"])
def regenerate():
    body = request.get_json() or {}
    tab, profile = body.get("tab"), body.get("profile")
    if tab not in DOCS or not profile:
        return jsonify({"error": "Bad request."}), 400
    try:
        docs = {k: (body.get("docs") or {}).get(k, "") for k in DOCS}
        docs[tab] = ask_llm(make_prompts(profile)[tab])
        consistency = check_consistency(profile, docs)
        if body.get("id"):
            with db() as con:
                con.execute("UPDATE profiles SET data=? WHERE id=?",
                            (json.dumps({"profile": profile, **docs, "consistency": consistency}), body["id"]))
        return jsonify({"text": docs[tab], "consistency": consistency})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/history")
def history():
    with db() as con:
        rows = con.execute("SELECT id, name, created FROM profiles ORDER BY id DESC LIMIT 20").fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/history/<int:pid>")
def history_item(pid):
    with db() as con:
        row = con.execute("SELECT data FROM profiles WHERE id=?", (pid,)).fetchone()
    if not row:
        return jsonify({"error": "Not found."}), 404
    return jsonify({"id": pid, **json.loads(row["data"])})


if __name__ == "__main__":
    app.run(debug=True)
