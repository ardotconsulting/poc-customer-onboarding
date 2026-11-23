#!/usr/bin/env python3
"""Customer Onboarding Pipeline Tracker POC — single-file Flask app.

Interactive onboarding pipeline tracker with 5 stages, progress bar,
and audit log. Visitors can walk through each stage, check off tasks,
see what's automated vs. human-in-the-loop, and track progress.

No external dependencies beyond Flask (pip-installed in the Docker image).
"""

import json
import os
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)

DATA_FILE = "/data/onboarding_state.json"

PIPELINE_STAGES = [
    {
        "stage": "Stage 1 — Deal Closed: Kickoff Trigger",
        "description": "When a deal moves to Closed Won, the onboarding pipeline fires automatically.",
        "items": [
            {"label": "n8n detects deal stage change in Odoo", "type": "automated"},
            {"label": "Ollama drafts welcome email with Cal.com booking link", "type": "automated"},
            {"label": "Mattermost notification sent to team channel", "type": "automated"},
            {"label": "Odoo project created with onboarding task template", "type": "automated"},
            {"label": "Review and send AI-drafted welcome email", "type": "human"},
        ],
    },
    {
        "stage": "Stage 2 — Account Setup and Provisioning",
        "description": "Once the kickoff call is scheduled, automated provisioning kicks in.",
        "items": [
            {"label": "Nextcloud folder created with share link", "type": "automated"},
            {"label": "BookStack space created with onboarding guide template", "type": "automated"},
            {"label": "Documenso envelope sent for signatures (if needed)", "type": "automated"},
            {"label": "Access credentials organized in Nextcloud", "type": "automated"},
            {"label": "Review folder structure and BookStack content", "type": "human"},
        ],
    },
    {
        "stage": "Stage 3 — Kickoff Call and Data Collection",
        "description": "The call is human, but everything around it is automated.",
        "items": [
            {"label": "24-hour reminder email sent with agenda", "type": "automated"},
            {"label": "Conduct the kickoff call", "type": "human"},
            {"label": "Ollama extracts action items from call notes", "type": "automated"},
            {"label": "Ollama generates call summary for customer", "type": "automated"},
            {"label": "Follow-up email drafted with action items", "type": "automated"},
            {"label": "Review and send follow-up email", "type": "human"},
        ],
    },
    {
        "stage": "Stage 4 — Training and Documentation",
        "description": "Systematize training so every customer gets consistent materials.",
        "items": [
            {"label": "BookStack documentation links added to Odoo task", "type": "automated"},
            {"label": "Ollama generates customer-specific user guide", "type": "automated"},
            {"label": "Training sessions scheduled via Cal.com", "type": "automated"},
            {"label": "Automated reminders sent before each session", "type": "automated"},
            {"label": "Feedback form (OpnForm) sent after each session", "type": "automated"},
            {"label": "Conduct training sessions", "type": "human"},
        ],
    },
    {
        "stage": "Stage 5 — First Milestone Check-In",
        "description": "Two weeks after onboarding starts, the check-in workflow triggers.",
        "items": [
            {"label": "Status report generated from Odoo task data", "type": "automated"},
            {"label": "Ollama summarizes progress for check-in email", "type": "automated"},
            {"label": "Overdue task reminders sent to assigned team members", "type": "automated"},
            {"label": "Customer satisfaction survey (OpnForm) sent", "type": "automated"},
            {"label": "Review check-in email and send to customer", "type": "human"},
        ],
    },
]


def _all_items():
    items = []
    for stage in PIPELINE_STAGES:
        for item in stage["items"]:
            items.append(item["label"])
    return items


def _load_state():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"checked": {}, "audit_log": []}


def _save_state(state):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _add_audit(state, action, item):
    state["audit_log"].append(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "action": action,
            "item": item,
        }
    )
    state["audit_log"] = state["audit_log"][-200:]


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Customer Onboarding Pipeline — ARDOT Consulting POC</title>
<style>
  :root {
    --bg: #0f1117; --card: #1a1d27; --accent: #4f9cf9; --text: #e0e0e0;
    --muted: #888; --green: #4caf50; --border: #2a2d3a; --amber: #ffa726;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: var(--bg); color: var(--text); line-height: 1.6; padding: 2rem 1rem; }
  .container { max-width: 900px; margin: 0 auto; }
  h1 { font-size: 1.8rem; margin-bottom: 0.25rem; }
  .subtitle { color: var(--muted); margin-bottom: 1.5rem; font-size: 0.95rem; }
  .subtitle a { color: var(--accent); text-decoration: none; }
  .progress-bar { background: var(--border); border-radius: 8px; height: 24px;
                  margin-bottom: 1.5rem; overflow: hidden; position: relative; }
  .progress-fill { background: var(--green); height: 100%; border-radius: 8px;
                   transition: width 0.4s ease; display: flex; align-items: center;
                   justify-content: center; font-size: 0.8rem; font-weight: bold; color: #fff;
                   min-width: 0; }
  .progress-text { position: absolute; left: 50%; top: 50%; transform: translate(-50%,-50%);
                   font-size: 0.8rem; color: var(--text); }
  .stats { display: flex; gap: 1rem; margin-bottom: 1.5rem; }
  .stat { background: var(--card); border: 1px solid var(--border); border-radius: 10px;
          padding: 0.8rem 1.2rem; flex: 1; text-align: center; }
  .stat-value { font-size: 1.5rem; font-weight: bold; }
  .stat-label { font-size: 0.8rem; color: var(--muted); }
  .stat-value.automated { color: var(--accent); }
  .stat-value.human { color: var(--amber); }
  .stat-value.done { color: var(--green); }
  .stage { background: var(--card); border: 1px solid var(--border); border-radius: 12px;
           margin-bottom: 1rem; overflow: hidden; }
  .stage-header { padding: 0.8rem 1.2rem; font-weight: 600; font-size: 1.05rem;
                  border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; }
  .stage-count { color: var(--muted); font-size: 0.85rem; font-weight: 400; }
  .stage-desc { padding: 0.5rem 1.2rem; font-size: 0.85rem; color: var(--muted); border-bottom: 1px solid var(--border); }
  .item { padding: 0.6rem 1.2rem; border-bottom: 1px solid var(--border); cursor: pointer;
          display: flex; align-items: center; gap: 0.6rem; transition: background 0.15s; }
  .item:hover { background: rgba(255,255,255,0.03); }
  .item:last-child { border-bottom: none; }
  .checkbox { width: 20px; height: 20px; border: 2px solid var(--muted); border-radius: 4px;
              flex-shrink: 0; display: flex; align-items: center; justify-content: center; }
  .item.checked .checkbox { background: var(--green); border-color: var(--green); }
  .item.checked .checkbox::after { content: '✓'; color: #fff; font-size: 14px; }
  .item.checked .item-label { text-decoration: line-through; color: var(--muted); }
  .badge { font-size: 0.7rem; padding: 0.15rem 0.5rem; border-radius: 4px; font-weight: 600;
           text-transform: uppercase; letter-spacing: 0.5px; margin-left: auto; }
  .badge.automated { background: rgba(79,156,249,0.15); color: var(--accent); }
  .badge.human { background: rgba(255,167,38,0.15); color: var(--amber); }
  .audit-section { margin-top: 2rem; }
  .audit-section h2 { font-size: 1.2rem; margin-bottom: 0.75rem; }
  .audit-log { background: var(--card); border: 1px solid var(--border); border-radius: 12px;
               padding: 1rem 1.2rem; max-height: 300px; overflow-y: auto; font-size: 0.85rem; }
  .audit-entry { padding: 0.3rem 0; border-bottom: 1px solid var(--border); color: var(--muted); }
  .audit-entry:last-child { border-bottom: none; }
  .audit-entry .action { font-weight: 600; color: var(--text); }
  .audit-entry .ts { color: var(--accent); font-size: 0.8rem; }
  .reset-btn { margin-top: 1.5rem; padding: 0.5rem 1.2rem; background: var(--card);
               border: 1px solid var(--border); border-radius: 8px; color: var(--muted);
               cursor: pointer; font-size: 0.85rem; }
  .reset-btn:hover { border-color: #e53935; color: #e53935; }
  .footer { margin-top: 2rem; text-align: center; color: var(--muted); font-size: 0.8rem; }
  .footer a { color: var(--accent); text-decoration: none; }
</style>
</head>
<body>
<div class="container">
  <h1>Customer Onboarding Pipeline Tracker</h1>
  <p class="subtitle">Interactive demo from
    <a href="https://www.ardotconsulting.com/2026/11/21/automating-customer-onboarding-with-open-source-tools/">Automating Customer Onboarding with Open Source Tools</a>
  </p>

  <div class="stats">
    <div class="stat">
      <div class="stat-value done" id="stat-done">0</div>
      <div class="stat-label">Completed</div>
    </div>
    <div class="stat">
      <div class="stat-value automated" id="stat-automated">0</div>
      <div class="stat-label">Automated Steps</div>
    </div>
    <div class="stat">
      <div class="stat-value human" id="stat-human">0</div>
      <div class="stat-label">Human-in-Loop</div>
    </div>
  </div>

  <div class="progress-bar">
    <div class="progress-fill" id="progress-fill" style="width:0%"></div>
    <span class="progress-text" id="progress-text">0 / 0 completed</span>
  </div>

  <div id="pipeline"></div>

  <div class="audit-section">
    <h2>Audit Log</h2>
    <div class="audit-log" id="audit-log">
      <div class="audit-entry" style="text-align:center">No actions yet. Click items to start tracking.</div>
    </div>
  </div>

  <button class="reset-btn" onclick="resetAll()">Reset pipeline</button>

  <div class="footer">
    <p>Proof of concept by <a href="https://www.ardotconsulting.com">ARDOT Consulting</a></p>
  </div>
</div>

<script>
const stages = {{ stages_json | safe }};
let checked = {{ checked_json | safe }};
const allItems = [];

stages.forEach(stage => {
  stage.items.forEach(item => allItems.push(item));
});

function toggleItem(item) {
  fetch('/api/toggle', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({item: item})
  })
  .then(r => r.json())
  .then(data => {
    checked = data.checked;
    render();
  });
}

function resetAll() {
  fetch('/api/reset', {method: 'POST'})
  .then(r => r.json())
  .then(data => {
    checked = {};
    render();
  });
}

function render() {
  const done = Object.values(checked).filter(v => v).length;
  const total = allItems.length;
  const automatedTotal = allItems.filter(i => i.type === 'automated').length;
  const humanTotal = allItems.filter(i => i.type === 'human').length;
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;

  document.getElementById('progress-fill').style.width = pct + '%';
  document.getElementById('progress-text').textContent = done + ' / ' + total + ' completed';
  document.getElementById('stat-done').textContent = done;
  document.getElementById('stat-automated').textContent = automatedTotal;
  document.getElementById('stat-human').textContent = humanTotal;

  const container = document.getElementById('pipeline');
  container.innerHTML = '';
  stages.forEach(stage => {
    const stageDone = stage.items.filter(i => checked[i.label]).length;
    const div = document.createElement('div');
    div.className = 'stage';
    div.innerHTML = '<div class="stage-header">' + stage.stage +
      '<span class="stage-count">' + stageDone + '/' + stage.items.length + '</span></div>' +
      '<div class="stage-desc">' + stage.description + '</div>';
    stage.items.forEach(item => {
      const itemDiv = document.createElement('div');
      itemDiv.className = 'item' + (checked[item.label] ? ' checked' : '');
      const badge = '<span class="badge ' + item.type + '">' + (item.type === 'automated' ? 'Auto' : 'Human') + '</span>';
      itemDiv.innerHTML = '<div class="checkbox"></div><span class="item-label">' + item.label + '</span>' + badge;
      itemDiv.onclick = () => toggleItem(item.label);
      div.appendChild(itemDiv);
    });
    container.appendChild(div);
  });

  fetch('/api/audit').then(r => r.json()).then(data => {
    const logDiv = document.getElementById('audit-log');
    if (!data.entries || data.entries.length === 0) {
      logDiv.innerHTML = '<div class="audit-entry" style="text-align:center">No actions yet. Click items to start tracking.</div>';
    } else {
      logDiv.innerHTML = data.entries.slice().reverse().map(e =>
        '<div class="audit-entry"><span class="action">' + e.action + '</span> ' + e.item +
        ' <span class="ts">\u2014 ' + e.timestamp + '</span></div>'
      ).join('');
    }
  });
}

render();
</script>
</body>
</html>
"""


@app.route("/")
def index():
    state = _load_state()
    return render_template_string(
        HTML_TEMPLATE,
        stages_json=json.dumps(PIPELINE_STAGES),
        checked_json=json.dumps(state.get("checked", {})),
    )


@app.route("/api/toggle", methods=["POST"])
def toggle():
    data =  request.get_json()
    item = data.get("item", "")
    state = _load_state()
    current = state.get("checked", {}).get(item, False)
    state.setdefault("checked", {})[item] = not current
    action = "Checked" if not current else "Unchecked"
    _add_audit(state, action, item)
    _save_state(state)
    return jsonify({"checked": state["checked"]})


@app.route("/api/audit")
def audit():
    state = _load_state()
    return jsonify({"entries": state.get("audit_log", [])})


@app.route("/api/reset", methods=["POST"])
def reset():
    state = {"checked": {}, "audit_log": []}
    _save_state(state)
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 80))
    app.run(host="0.0.0.0", port=port)
