# AI Projects: Career Profile Generator and Meeting-to-Action Assistant

Two small Flask web apps that use the Groq API (free tier). Each folder is independent.

| Project | Folder | Port |
|---|---|---|
| M1-P1 Personalized Career Content Generator | `career_generator` | 5000 |
| M1-P2 Meeting-to-Action Assistant | `meeting_assistant` | 5001 |

## Run (either project)
```
cd career_generator        # or meeting_assistant
pip install -r requirements.txt
copy .env.example .env     # macOS/Linux: cp .env.example .env
# open .env and paste your key from console.groq.com
python app.py
```
Then open http://127.0.0.1:5000 (career) or http://127.0.0.1:5001 (meeting).

## How they work
**Career generator:** form -> AI builds one master profile -> you review and edit it -> four documents (summary, skill gap, learning plan, interview prep) are written from that same profile -> a consistency check compares them -> saved to SQLite.

**Meeting assistant:** transcript -> AI extracts summary, decisions, tasks, follow-ups as JSON -> plain Python flags tasks with a missing or vague owner, deadline or description -> the user answers clarification questions -> Python re-checks.

## Known limits
- AI output can be wrong. Check it against the source.
- Free-tier rate limits apply; the app waits and retries, so long runs can be slow.
- Groq retires models over time. Set `GROQ_MODEL` in `.env` if you get a "Not Found" error.
- Meeting assistant: transcripts are capped at 15,000 characters.
