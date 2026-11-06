const $ = (id) => document.getElementById(id);
const TABS = { summary: "Summary", skill_gap: "Skill gap", learning: "Learning plan",
               interview: "Interview prep", consistency: "Consistency check" };
const DOCS = ["summary", "skill_gap", "learning", "interview"];
let data = null;      // last full result
let profile = null;   // profile being reviewed
let current = "summary";

const panels = ["empty", "loading", "review", "output"];
const show = (name) => panels.forEach((p) => ($(p).hidden = p !== name));
const split = (s) => s.split(",").map((x) => x.trim()).filter(Boolean);
const render = (md) => DOMPurify.sanitize(marked.parse(md));

async function post(url, body) {
  const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" },
                                 body: JSON.stringify(body) });
  const json = await res.json();
  if (!res.ok) throw new Error(json.error || "Something went wrong.");
  return json;
}

// Step 1: build the profile and let the user edit it
$("form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("error").textContent = "";
  $("go").disabled = true;
  $("loadMsg").textContent = "Reading your details...";
  show("loading");
  try {
    profile = await post("/profile", Object.fromEntries(new FormData($("form"))));
    $("r_role").value = profile.target_role;
    $("r_level").value = profile.experience_level;
    $("r_skills").value = profile.current_skills.join(", ");
    $("r_interests").value = profile.interests.join(", ");
    $("r_strengths").value = profile.strengths.join(", ");
    show("review");
  } catch (err) {
    $("error").textContent = err.message;
    show("empty");
  } finally { $("go").disabled = false; }
});

// Step 2: write the documents from the (edited) profile
$("generate").addEventListener("click", async () => {
  $("error").textContent = "";
  $("loadMsg").textContent = "Writing your documents and checking they agree. This can take up to a minute.";
  show("loading");
  const edited = { ...profile, target_role: $("r_role").value.trim(), experience_level: $("r_level").value,
    current_skills: split($("r_skills").value), interests: split($("r_interests").value),
    strengths: split($("r_strengths").value) };
  try {
    data = await post("/generate", { profile: edited });
    openResult();
    loadHistory();
  } catch (err) {
    $("error").textContent = err.message;
    show("review");
  }
});

function openResult() {
  $("tabs").innerHTML = "";
  for (const key in TABS) {
    const b = document.createElement("button");
    b.textContent = TABS[key];
    b.dataset.tab = key;
    b.addEventListener("click", () => showTab(key));
    $("tabs").appendChild(b);
  }
  show("output");
  showTab("summary");
}

function showTab(name) {
  current = name;
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  $("content").innerHTML = render(data[name]);
  $("regen").hidden = name === "consistency";
}

$("regen").addEventListener("click", async () => {
  $("regen").disabled = true;
  $("regen").textContent = "Regenerating...";
  try {
    const out = await post("/regenerate", { id: data.id, profile: data.profile, tab: current, docs: data });
    data[current] = out.text;
    data.consistency = out.consistency;
    showTab(current);
  } catch (err) { $("error").textContent = err.message; }
  $("regen").disabled = false;
  $("regen").textContent = "Regenerate this tab";
});

$("copy").addEventListener("click", async () => {
  await navigator.clipboard.writeText(data[current]);
  $("copy").textContent = "Copied";
  setTimeout(() => ($("copy").textContent = "Copy"), 1500);
});

$("txt").addEventListener("click", () => {
  const text = DOCS.map((k) => `${TABS[k].toUpperCase()}\n${"=".repeat(TABS[k].length)}\n${data[k]}`).join("\n\n\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
  a.download = `${data.profile.name || "career"}_profile.txt`;
  a.click();
});

// PDF: fill a hidden print-only area with all four documents, then print (choose "Save as PDF")
$("pdf").addEventListener("click", () => {
  $("printable").innerHTML = DOCS.map((k) => `<h1>${TABS[k]}</h1>` + render(data[k])).join("");
  window.print();
});

// Past profiles
async function loadHistory() {
  const rows = await (await fetch("/history")).json();
  $("historyList").innerHTML = "";
  if (!rows.length) { $("historyList").textContent = "Nothing saved yet."; return; }
  rows.forEach((r) => {
    const li = document.createElement("li");
    const b = document.createElement("button");
    b.textContent = r.name;
    const small = document.createElement("small");
    small.textContent = r.created;
    b.appendChild(small);
    b.addEventListener("click", async () => {
      data = await (await fetch(`/history/${r.id}`)).json();
      openResult();
    });
    li.appendChild(b);
    $("historyList").appendChild(li);
  });
}
loadHistory();
