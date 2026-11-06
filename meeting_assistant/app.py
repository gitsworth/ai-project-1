import json
import os
import time
from datetime import date

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

load_dotenv()
app = Flask(__name__)

API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
REQUIRED = ["title", "summary", "decisions", "tasks", "follow_ups"]

# Words that mean "nobody was really chosen" / "no real date was given"
VAGUE_OWNERS = {"", "tbd", "unassigned", "none", "someone", "somebody", "team",
                "everyone", "we", "all", "n/a", "unknown"}
VAGUE_DEADLINES = ("soon", "asap", "later", "sometime", "eventually", "tbd",
                   "when possible", "when ready", "n/a", "unknown", "no deadline")


def ask_llm(prompt):
    key = os.getenv("GROQ_API_KEY")
    if not key or key == "paste_your_key_here":
        raise RuntimeError("Add your Groq API key to the .env file.")
    body = {"model": MODEL, "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": prompt}]}
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


# ---------- Step 1: the LLM understands the transcript ----------
def extract(transcript):
    prompt = f"""You turn meeting transcripts into structured notes. Today's date is {date.today().isoformat()}.
Return ONLY a JSON object with these keys:
"title": short meeting title
"summary": 3 to 5 sentences
"decisions": list of strings, only things the group actually agreed
"tasks": list of objects, each {{"task": "...", "owner": "...", "deadline": "..."}}
"follow_ups": list of strings (things to revisit, next meeting, open questions)
Rules:
- Use the speakers' names exactly as written in the transcript.
- If the owner or deadline was NOT clearly stated, set it to null. Never guess.
- Do NOT convert deadlines to dates. Copy the deadline words as spoken (for example "Wednesday" or "by the 30th").
- Decisions are only things the group agreed on, such as dates, choices or budgets. Never put task assignments in decisions.
- Do not list meetings or reminders as tasks. Put them in follow_ups.
- If someone says something should be done but nobody commits ("we should look into X"), still list it as a task with owner null.

TRANSCRIPT:
{transcript}"""
    for _ in range(2):  # try twice
        try:
            data = json.loads(ask_llm(prompt))
            if all(k in data for k in REQUIRED) and isinstance(data["tasks"], list):
                data["tasks"] = [t for t in data["tasks"] if isinstance(t, dict)]
                return data
        except json.JSONDecodeError:
            pass
    raise RuntimeError("The AI returned unusable notes twice. Please try again.")


# ---------- Step 2: plain Python finds what is missing or ambiguous ----------
def text(v):
    return str(v).strip() if v else ""


def find_issues(tasks):
    """Returns {task_index: [{field, question}, ...]} for every incomplete task."""
    issues = {}
    for i, t in enumerate(tasks):
        name, owner, deadline = text(t.get("task")), text(t.get("owner")), text(t.get("deadline"))
        label = name or "this action"
        problems = []
        if len(name.split()) < 3:
            problems.append({"field": "task", "question": f'"{label}" is too vague. What exactly needs to be done?'})
        if owner.lower() in VAGUE_OWNERS:
            problems.append({"field": "owner", "question": f'Who owns "{label}"?'})
        if not deadline or any(w in deadline.lower() for w in VAGUE_DEADLINES):
            problems.append({"field": "deadline", "question": f'What is the deadline for "{label}"?'})
        if problems:
            issues[i] = problems
    return issues


# ---------- routes ----------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/extract", methods=["POST"])
def extract_route():
    transcript = ((request.get_json() or {}).get("transcript") or "").strip()
    if len(transcript) < 50:
        return jsonify({"error": "The transcript is too short. Paste at least a few sentences."}), 400
    if len(transcript) > 15000:
        return jsonify({"error": "The transcript is too long (15,000 characters max)."}), 400
    try:
        result = extract(transcript)
        return jsonify({"result": result, "issues": find_issues(result["tasks"])})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/validate", methods=["POST"])
def validate_route():
    tasks = (request.get_json() or {}).get("tasks") or []
    return jsonify({"issues": find_issues(tasks)})


if __name__ == "__main__":
    app.run(debug=True, port=5001)  # port 5001 so it can run next to the career app
