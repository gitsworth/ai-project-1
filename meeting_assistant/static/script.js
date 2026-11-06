const $ = (id) => document.getElementById(id);
const panels = ["empty", "loading", "output"];
const show = (n) => panels.forEach((p) => ($(p).hidden = p !== n));
let result = null;   // summary, decisions, tasks, follow_ups
let issues = {};     // task index -> list of problems (decided by Python)

const SAMPLE = `Priya: Let's start with the website launch. Rahul, can you finish the landing page?
Rahul: Yes, I'll have it done by Friday.
Priya: Great. We also decided to go with the blue theme for the launch.
Sam: Someone should contact the printing vendor about the brochures.
Priya: Agreed, let's do that soon.
Rahul: I'll also look into analytics.
Priya: Okay. Let's meet again next Tuesday to review progress.
Sam: I'll send the budget report to finance by the 30th.`;

// Build elements with textContent only, so transcript text can never inject HTML
function el(tag, text, cls) {
  const e = document.createElement(tag);
  if (text !== undefined) e.textContent = text;
  if (cls) e.className = cls;
  return e;
}

async function post(url, body) {
  const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const json = await res.json();
  if (!res.ok) throw new Error(json.error || "Something went wrong.");
  return json;
}

$("sample").addEventListener("click", () => ($("transcript").value = SAMPLE));

$("form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("error").textContent = "";
  $("go").disabled = true;
  show("loading");
  try {
    const out = await post("/extract", { transcript: $("transcript").value });
    result = out.result;
    issues = out.issues;
    draw();
    show("output");
  } catch (err) {
    $("error").textContent = err.message;
    show("empty");
  } finally { $("go").disabled = false; }
});

function fillList(ul, items) {
  ul.innerHTML = "";
  (items.length ? items : ["None recorded."]).forEach((x) => ul.appendChild(el("li", String(x))));
}

function draw() {
  $("title").textContent = result.title;
  $("summary").textContent = result.summary;
  fillList($("decisions"), result.decisions);
  fillList($("followups"), result.follow_ups);

  $("taskBody").innerHTML = "";
  result.tasks.forEach((t, i) => {
    const tr = el("tr");
    tr.appendChild(el("td", t.task || "(no description)"));
    for (const f of ["owner", "deadline"]) {
      tr.appendChild(t[f] ? el("td", t[f]) : el("td", f === "owner" ? "Not assigned" : "No deadline", "missing"));
    }
    const status = el("td");
    status.appendChild(issues[i] ? el("span", "Needs clarification", "tag flag") : el("span", "Complete", "tag ok"));
    tr.appendChild(status);
    $("taskBody").appendChild(tr);
  });

  const open = Object.keys(issues);
  $("status").textContent = open.length
    ? `${open.length} of ${result.tasks.length} action items are incomplete.`
    : "All action items have an owner and a deadline.";
  $("clarify").hidden = !open.length;
  $("questions").innerHTML = "";
  open.forEach((i) => issues[i].forEach((p) => {
    const label = el("label", p.question);
    const input = el("input");
    input.dataset.index = i;
    input.dataset.field = p.field;
    label.appendChild(input);
    $("questions").appendChild(label);
  }));
}

// The user answers; Python re-checks everything
$("clarify").addEventListener("submit", async (e) => {
  e.preventDefault();
  document.querySelectorAll("#questions input").forEach((inp) => {
    if (inp.value.trim()) result.tasks[inp.dataset.index][inp.dataset.field] = inp.value.trim();
  });
  try {
    issues = (await post("/validate", { tasks: result.tasks })).issues;
    draw();
  } catch (err) { $("error").textContent = err.message; }
});

function download(name, content, type) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([content], { type }));
  a.download = name;
  a.click();
}

$("dlTxt").addEventListener("click", () => {
  const tasks = result.tasks.map((t, i) =>
    `${i + 1}. ${t.task || "(no description)"} | Owner: ${t.owner || "NOT ASSIGNED"} | Deadline: ${t.deadline || "NONE"}${issues[i] ? "  [NEEDS CLARIFICATION]" : ""}`);
  const bullets = (a) => (a.length ? a.map((x) => "- " + x) : ["- None"]);
  download("meeting_report.txt", [result.title, "", "SUMMARY", result.summary, "", "DECISIONS", ...bullets(result.decisions),
    "", "ACTION ITEMS", ...tasks, "", "FOLLOW-UPS", ...bullets(result.follow_ups)].join("\n"), "text/plain");
});

$("dlCsv").addEventListener("click", () => {
  const q = (v) => `"${String(v || "").replace(/"/g, '""')}"`;
  const rows = result.tasks.map((t, i) => [t.task, t.owner, t.deadline, issues[i] ? "Needs clarification" : "Complete"].map(q).join(","));
  download("tasks.csv", ["Task,Owner,Deadline,Status", ...rows].join("\n"), "text/csv");
});
