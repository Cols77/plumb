"""R11 measured (sp2 9.3, SR-043 EX-2 and EX-3): one ambiguous request, four drafted
questions, exactly the two that matter remain; recorded as two DECs with matters true, the
stop hook asks the first in the next message and the second only after it is answered."""

from __future__ import annotations

import io
import json
import re
import subprocess
import time
from pathlib import Path

import pytest
from capture_helpers import log_prompt, record_text, run, write_stated
from logutil import legacy_relay

from plumb.api import open_core
from plumb.hosts.claude_code import stop

pytestmark = pytest.mark.sr("SR-043")

REQUEST = "let users export their data"
QUESTIONS = [
    {"question": "Which file format should the export use?", "options": ["CSV", "JSON"],
     "recommended": "CSV"},
    {"question": "Should the download button be blue or green?",
     "options": [{"label": "blue", "will": ["a download button on the account page"]},
                 {"label": "green", "will": ["a download button on the account page"]}]},
    {"question": "Which data goes in: the orders only, or orders and invoices?",
     "options": [{"label": "orders only", "will": ["orders"], "wont": ["invoices"]},
                 {"label": "orders and invoices", "will": ["orders", "invoices"]}],
     "recommended": "orders only"},
    {"question": "Who may export: every user, or only administrators?",
     "options": [{"label": "every user", "will": ["export for every user"]},
                 {"label": "administrators", "will": ["export for administrators"],
                  "wont": ["export for other users"]}],
     "recommended": "every user"},
]


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def project(repo: Path, write_record) -> Path:
    from plumb.approvals import approve
    from plumb.contracts import Target

    write_record(repo, record_text(
        "SR-002", "Exports are CSV files", statement="An export is written as a CSV file",
        examples=[{"id": "EX-1", "given": "a user with 2 orders", "when": "the export runs",
                   "then": "a CSV file with 2 rows is written"}]))
    (repo / "src").mkdir()
    (repo / "src" / "export.py").write_text("def export():\n    pass\n", encoding="utf-8")
    open_core(repo).add_link("SR-002", "implemented_by", Target(path="src/export.py"))
    approve(open_core(repo), ["SR-002"])
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "setup")
    return repo


def start_turn(repo: Path, asked: dict | None = None) -> None:
    path = repo / ".plumb" / "session" / "s1" / "turn.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    kept = asked if asked is not None else previous.get("asked", {})
    path.write_text(json.dumps({"turn_start": time.time() - 0.5,
                                "prompt_digest": "sha256:" + "a" * 64,
                                "asked": kept}), encoding="utf-8")
    touched = path.parent / "touched.txt"
    if touched.exists():
        touched.unlink()


def run_stop(repo: Path, hook_input) -> str | None:
    out = io.StringIO()
    payload = hook_input("Stop", session_id="s1", stop_hook_active=False)
    assert stop.main(stdin=io.StringIO(payload), stdout=out, root=repo, verify=None,
                     unjudged=None) == 0
    text = out.getvalue()
    if not text.strip():
        return None
    data = json.loads(text)
    return data["reason"] if data.get("decision") == "block" else None


def asked_decs(reason: str | None) -> list[str]:
    return re.findall(r"plumb: (DEC-\d+) is unconfirmed", reason or "")


def test_ambiguous_request_yields_exactly_the_questions_that_matter(
        project: Path, hook_input, monkeypatch, capsys) -> None:
    drafts = project / "questions.json"
    drafts.write_text(json.dumps(QUESTIONS), encoding="utf-8")
    assert run(project, "clarify", REQUEST, "--questions", str(drafts), "--json") == 0
    view = json.loads(capsys.readouterr().out)
    assert view["depth"] == "incremental"
    kept = [q["question"] for q in view["questions"]]
    assert kept == [QUESTIONS[2]["question"], QUESTIONS[3]["question"]]
    reasons = {q["question"]: q["dropped_because"] for q in view["dropped"]}
    assert reasons[QUESTIONS[0]["question"]].startswith("answered by SR-002 (confirmed)")
    assert reasons[QUESTIONS[1]["question"]] == "every option builds the same thing"

    # the agent records each question that matters as a DEC (matters, recommended)
    start_turn(project, asked={})
    for q in view["questions"]:
        labels = [o["label"] for o in q["options"]]
        other = next(x for x in labels if x != q["recommended"])
        assert run(project, "decide", "--question", q["question"], "--chosen",
                   q["recommended"], "--alt", other, "--matters", "--recommend",
                   q["recommended"], "--decides", "SR-002") == 0
    index = open_core(project).index()
    decs = sorted(i for i in index if i.startswith("DEC-"))
    assert decs == ["DEC-001", "DEC-002"]
    assert all(index[d].fields["matters"] is True for d in decs)

    # the next message asks only the first
    assert asked_decs(run_stop(project, hook_input)) == ["DEC-001"]
    # a later turn on the same work, the first still unanswered: nothing new is asked
    start_turn(project)
    (project / "src" / "export.py").write_text("def export():\n    return 1\n", "utf-8")
    assert asked_decs(run_stop(project, hook_input)) == []

    # the owner answers the first ("ok" to DEC-001); the next stop asks the second
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "s1")
    write_stated(project, [("DEC-001", open_core(project).index()["DEC-001"].hash)],
                 at="2026-10-06T09:00:00Z")
    digest = log_prompt(project, "ok, orders only", at="2026-10-06T09:01:00Z")
    legacy_relay(project, ["DEC-001"], digest, "ok", stated=["DEC-001"])
    start_turn(project)
    (project / "src" / "export.py").write_text("def export():\n    return 2\n", "utf-8")
    assert asked_decs(run_stop(project, hook_input)) == ["DEC-002"]
