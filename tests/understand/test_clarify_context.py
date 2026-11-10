"""SR-128: the clarify check reads the conversation before the message (the agent's last reply,
the owner's previous messages) and the repository facts, and uses them to resolve references
to earlier turns; without a transcript it runs on the message alone, as before."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from capture.capture_helpers import log_prompt

from iaso.api import open_core
from iaso.understand import clarify, evalrun, files, gate, worker

pytestmark = pytest.mark.sr("SR-223")

SESSION = "s1"
REQUEST = "Resolve all of the findings using a workflow."
FINDINGS = "## Findings\n1. The exit code is lost.\n2. `/iaso init` does nothing."


def _owner(text: str, **extra: Any) -> dict[str, Any]:
    return {"type": "user", "message": {"role": "user", "content": text}, **extra}


def _agent(*texts: str, tool: bool = False) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = [{"type": "text", "text": t} for t in texts]
    if tool:
        blocks.append({"type": "tool_use", "id": "t1", "name": "Bash", "input": {}})
    return {"type": "assistant", "message": {"role": "assistant", "content": blocks}}


def _tool_result() -> dict[str, Any]:
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t1", "content": "lots of output"}]}}


def _transcript(path: Path, entries: list[dict[str, Any]]) -> Path:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for entry in entries:
            handle.write(json.dumps(entry) + "\n")
    return path


def _review_session(tmp_path: Path, *, with_request: bool) -> Path:
    entries = [
        _owner("hello there"),
        _agent("Hi."),
        _owner("Using plugin-dev, review the plugin artifacts. Any improvements?"),
        _agent("I'll look at the plugin.", tool=True),
        _tool_result(),
        _owner("<task-notification>a background task finished</task-notification>"),
        _owner("Base directory for this skill: ...", isMeta=True),
        _agent("inner work", tool=True) | {"isSidechain": True},
        _agent(FINDINGS),
        {"type": "system", "content": "stop hook ran"},
    ]
    if with_request:
        entries.append(_owner(REQUEST))
    return _transcript(tmp_path / "t.jsonl", entries)


# ---------------------------------------------------------------- reading the transcript


@pytest.mark.parametrize("with_request", [False, True])
def test_ex1_the_last_reply_and_earlier_messages_come_from_the_transcript(
        tmp_path: Path, with_request: bool) -> None:
    path = _review_session(tmp_path, with_request=with_request)
    talk = clarify.conversation(str(path), REQUEST)
    assert talk is not None
    # every reply text since the owner's previous message; tool calls, tool results,
    # injected entries, subagent turns and host notices are not the conversation
    assert talk["last_reply"] == "I'll look at the plugin.\n\n" + FINDINGS
    assert talk["earlier_messages"] == [
        "hello there", "Using plugin-dev, review the plugin artifacts. Any improvements?"]


def test_only_the_three_previous_owner_messages_are_kept(tmp_path: Path) -> None:
    entries: list[dict[str, Any]] = []
    for n in range(1, 6):
        entries += [_owner(f"message {n}"), _agent(f"reply {n}")]
    talk = clarify.conversation(str(_transcript(tmp_path / "t.jsonl", entries)), "message 6")
    assert talk is not None
    assert talk["earlier_messages"] == ["message 3", "message 4", "message 5"]
    assert talk["last_reply"] == "reply 5"


def test_the_budget_keeps_the_end_of_the_reply_and_the_start_of_each_message(
        tmp_path: Path) -> None:
    long_reply = "start of the reply " + "x" * 9000 + " the question at the end?"
    long_ask = "please look at this " + "y" * 2000
    path = _transcript(tmp_path / "t.jsonl", [_owner(long_ask), _agent(long_reply)])
    talk = clarify.conversation(str(path), "do it")
    assert talk is not None
    reply = talk["last_reply"]
    assert len(reply) <= clarify.REPLY_BUDGET
    assert reply.startswith(clarify.CUT) and reply.endswith("the question at the end?")
    assert "start of the reply" not in reply
    (ask,) = talk["earlier_messages"]
    assert len(ask) <= clarify.EARLIER_BUDGET
    assert ask.startswith("please look at this") and ask.endswith(clarify.CUT)


def test_a_short_reply_and_message_are_not_cut(tmp_path: Path) -> None:
    path = _transcript(tmp_path / "t.jsonl", [_owner("a"), _agent("b")])
    assert clarify.conversation(str(path), "c") == {"last_reply": "b",
                                                    "earlier_messages": ["a"]}


def test_a_long_transcript_is_read_from_its_end(tmp_path: Path) -> None:
    filler = [_agent("z" * 1000) for _ in range(600)]           # about 600 KB of replies
    entries = [_owner("the first ask"), *filler, _owner("the second ask"), _agent("done")]
    path = _transcript(tmp_path / "t.jsonl", entries)
    assert path.stat().st_size > clarify.TAIL_READS[0]
    talk = clarify.conversation(str(path), "next")
    assert talk is not None and talk["last_reply"] == "done"
    assert talk["earlier_messages"] == ["the first ask", "the second ask"]  # read further back


@pytest.mark.parametrize("transcript", [None, "", "does/not/exist.jsonl"])
def test_ex4_no_readable_transcript_no_conversation(transcript: Any) -> None:
    assert clarify.conversation(transcript, REQUEST) is None


def test_ex4_a_transcript_with_no_earlier_turn_gives_no_conversation(tmp_path: Path) -> None:
    path = _transcript(tmp_path / "t.jsonl", [_owner(REQUEST), {"garbage": True}])
    (tmp_path / "t.jsonl").open("a", encoding="utf-8").write("not json\n")
    assert clarify.conversation(str(path), REQUEST) is None


# ---------------------------------------------------------------- the repository facts


def test_ex3_the_repository_facts_come_from_git_files(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / ".git" / "refs" / "heads").mkdir(parents=True)
    (root / ".git" / "HEAD").write_text("ref: refs/heads/fix/plugin-review\n",
                                        encoding="utf-8")
    sub = root / "pkg"
    sub.mkdir()
    assert clarify.repository(root) == {"root": str(root), "git": True,
                                        "branch": "fix/plugin-review"}
    assert clarify.repository(sub)["git"] is True              # a folder inside it


def test_a_folder_outside_git_says_so(tmp_path: Path) -> None:
    assert clarify.repository(tmp_path / "plain") == {
        "root": str(tmp_path / "plain"), "git": False, "branch": ""} or \
        clarify.repository(tmp_path / "plain")["git"] is True   # tmp inside a checkout


# ---------------------------------------------------------------- the job and the hook


def _ctx(transcript: Path | None) -> SimpleNamespace:
    data = {"transcript_path": str(transcript)} if transcript else {}
    return SimpleNamespace(session_id=SESSION, data=data)


def _job(repo: Path) -> Any:
    (path,) = files.jobs_dir(repo, SESSION).glob("clarify-*.json")
    return files.job_from_json(json.loads(path.read_text(encoding="utf-8")))


def test_ex1_the_prompt_hook_puts_the_conversation_in_the_job_inputs(
        repo: Path, tmp_path: Path, engine_standins: Any) -> None:
    core = open_core(repo)
    transcript = _review_session(tmp_path, with_request=False)
    digest = log_prompt(repo, "/iaso clarify " + REQUEST, session=SESSION)
    clarify.on_prompt(_ctx(transcript), core, {"digest": digest, "text": "/iaso clarify " + REQUEST})
    job = _job(repo)
    assert job.inputs["context"]["last_reply"].endswith(FINDINGS)
    assert job.inputs["repository"]["root"] == str(repo)
    # the transcript keeps growing; the job still recomputes to what the owner saw
    with transcript.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_agent("a later reply")) + "\n")
    assert clarify.recompute(core, job) == job.inputs
    engine_standins.dispatcher.script = {"clarify": {"intent": "yes", "gap": False,
                                                     "gaps": []}}
    worker.run_once(core, SESSION, job.id)
    (sent,) = engine_standins.dispatcher.jobs
    assert sent.inputs["context"] == job.inputs["context"]       # the reader got it
    assert not gate.is_closed(repo, SESSION)


def test_ex4_without_a_transcript_the_check_runs_on_the_message_alone(
        repo: Path, engine_standins: Any) -> None:
    core = open_core(repo)
    digest = log_prompt(repo, "/iaso clarify " + REQUEST, session=SESSION)
    clarify.on_prompt(_ctx(None), core, {"digest": digest, "text": "/iaso clarify " + REQUEST})
    job = _job(repo)
    assert "context" not in job.inputs
    assert set(job.inputs) == {"message", "touched", "answered", "repository"}
    assert clarify.recompute(core, job) == job.inputs
    engine_standins.dispatcher.script = {"clarify": {"intent": "no", "gap": False,
                                                     "gaps": []}}
    worker.run_once(core, SESSION, job.id)
    assert engine_standins.dispatcher.jobs and not gate.is_closed(repo, SESSION)


def test_a_job_built_without_the_hook_recomputes_the_same(repo: Path) -> None:
    core = open_core(repo)
    digest = log_prompt(repo, "add a thing", session=SESSION)
    job = clarify.build(core, SESSION, message={"digest": digest, "text": "add a thing"})
    assert job is not None and clarify.recompute(core, job) == job.inputs


# ---------------------------------------------------------------- the reader's prompt and cases


def test_the_reader_is_told_to_resolve_references_and_never_guess_facts() -> None:
    prompt = (Path(clarify.__file__).parent / "agents" / "clarify.md").read_text(
        encoding="utf-8")
    assert "`context`" in prompt and "`repository`" in prompt
    assert "the findings above" in prompt and "it is not a gap" in prompt
    assert "Never state a fact about the repository or the conversation" in prompt


def test_ex1_ex2_ex3_the_misreads_of_this_session_are_frozen_cases() -> None:
    cases = {c["name"]: c for c in evalrun.load_cases("clarify")}
    for name, word in (("sr128-findings-after-review", "findings"),
                       ("sr128-fixes-for-this-issue", "this issue")):
        case = cases[name]
        assert word in case["inputs"]["message"]["text"]
        assert case["inputs"]["context"]["last_reply"]
        assert case["inputs"]["repository"]["git"] is True
        assert case["expect"] == {"intent": "yes", "gap": False}
        assert "not a git repository" in case["never_says"]


class _SaysNotARepo:
    """A clarifier that gets intent and gap right but states a fact its inputs never gave."""

    name = "says-not-a-repo"

    def available(self) -> None:
        return None

    def run(self, job: Any, **_: Any) -> dict[str, Any]:
        return {"intent": "yes", "gap": False, "gaps": [], "readback": {
            "will": [self.line]}}

    line = "The working folder is not a git repository, so start one."


def test_a_case_fails_when_the_answer_says_what_it_must_never_say() -> None:
    """SR-128 EX-3: the frozen sr128 cases fail a reader that claims the folder is not a git
    repository, even when its intent and gap are right."""
    from iaso.understand import evalrun

    cases = [c for c in evalrun.load_cases("clarify") if c.get("never_says")]
    assert cases
    results = evalrun.run_cases(_SaysNotARepo(), cases, "clarify")
    assert results and not any(r["passed"] or r.get("error") for r in results)
    honest = _SaysNotARepo()
    honest.line = "Resolve the four plugin-review findings listed above."
    assert all(r["passed"] for r in evalrun.run_cases(honest, cases, "clarify"))
    assert evalrun._says_none({"will": ["Fix the hook"]}, ["not a git repo"]) is True


# ---------------------------------------------------------------- after a /compact, other chats


def _summary(text: str) -> dict[str, Any]:
    return {"type": "user", "isCompactSummary": True, "isVisibleInTranscriptOnly": True,
            "message": {"role": "user", "content": text}}


SUMMARY = ("This session is being continued from a previous conversation that ran out of "
           "context. The summary below covers the earlier portion of the conversation.")


def test_ex2_a_compaction_summary_is_not_an_owner_message(tmp_path: Path) -> None:
    """After a /compact the agent's diagnosis is still the last reply, and the host's summary
    comes apart, never as the owner's words."""
    path = _transcript(tmp_path / "t.jsonl", [
        _owner("why does the panel not show?"), _agent("old reply"), _summary(SUMMARY),
        _owner("look again"), _agent("The panel is off: no session wrote host.json.")])
    talk = clarify.conversation(str(path), "apply the proposed fixes for this issue")
    assert talk is not None
    assert talk["last_reply"] == "The panel is off: no session wrote host.json."
    assert talk["earlier_messages"] == ["look again"]
    assert talk["summary"].startswith("This session is being continued")


def test_a_session_ended_by_its_compaction_keeps_its_last_turns(tmp_path: Path) -> None:
    path = _transcript(tmp_path / "t.jsonl", [
        _owner("why does the panel not show?"), _agent("Its hello is refused."), _summary(SUMMARY)])
    talk = clarify.conversation(str(path), "next")
    assert talk is not None
    assert talk["last_reply"] == "Its hello is refused."
    assert talk["earlier_messages"] == ["why does the panel not show?"]
    assert "summary" in talk


@pytest.mark.parametrize("text", ["<div>the band</div> looks wrong", "<b>fix it</b>"])
def test_pasted_markup_is_the_owners_words(tmp_path: Path, text: str) -> None:
    path = _transcript(tmp_path / "t.jsonl", [
        _owner(text), _owner("<command-name>/model</command-name>"),
        _owner("<local-command-stdout>Set model</local-command-stdout>"),
        _owner("<system-reminder>x</system-reminder>"), _agent("ok")])
    talk = clarify.conversation(str(path), "next")
    assert talk is not None and talk["earlier_messages"] == [text]


def test_other_recent_sessions_of_the_project_are_read(tmp_path: Path) -> None:
    """"The issue we detected in that chat": the owner's other recent sessions (the transcripts
    beside this one), the most recent first, at most OTHER_COUNT, none older than a week."""
    import os
    import time

    now = time.time()
    here = _transcript(tmp_path / "now.jsonl", [_owner("hi"), _agent("hello")])
    for name, age, reply in (("old.jsonl", 8 * 24 * 3600, "too old"),
                             ("a.jsonl", 3600, "The panel is off: hello refused on resume."),
                             ("b.jsonl", 7200, "second"), ("c.jsonl", 9000, "third")):
        path = _transcript(tmp_path / name, [_owner(f"ask {name}"), _agent(reply)])
        os.utime(path, (now - age, now - age))
    (tmp_path / "broken.jsonl").write_text("not json\n", encoding="utf-8")
    os.utime(tmp_path / "broken.jsonl", (now - 60, now - 60))
    others = clarify.other_sessions(here, now=now)
    assert [o["last_reply"] for o in others] == ["The panel is off: hello refused on resume.",
                                                 "second"]
    assert others[0]["earlier_messages"] == ["ask a.jsonl"] and others[0]["last_active"]


def test_the_frozen_context_carries_the_other_sessions(tmp_path: Path, repo: Path) -> None:
    folder = tmp_path / "project"
    folder.mkdir()
    _transcript(folder / "other.jsonl", [_owner("why is the panel off?"),
                                         _agent("Its hello is refused after a resume.")])
    here = _transcript(folder / "this.jsonl", [_owner("hi"), _agent("hello")])
    frozen = clarify.frozen_context(repo, SESSION, "sha256:" + "c" * 64, str(here), "fix it")
    (other,) = frozen["other_sessions"]
    assert other["last_reply"] == "Its hello is refused after a resume."


def test_a_reader_that_does_not_name_the_reference_fails_the_case() -> None:
    """The sr128 cases check the readback names what the reference points to (says_any)."""
    cases = [c for c in evalrun.load_cases("clarify") if c.get("says_any")]
    assert {c["name"] for c in cases} >= {"sr128-findings-after-review",
                                          "sr128-fixes-for-this-issue",
                                          "sr128-issue-from-another-chat"}
    vague = _SaysNotARepo()
    vague.line = "Do what was asked."
    assert not any(r["passed"] for r in evalrun.run_cases(vague, cases, "clarify"))
    named = _SaysNotARepo()
    named.line = "Fix why iaso's panel (the mod) stays off: the plugin-review findings."
    assert all(r["passed"] for r in evalrun.run_cases(named, cases, "clarify"))


def test_the_reader_is_told_about_other_sessions_and_the_summary() -> None:
    prompt = (Path(clarify.__file__).parent / "agents" / "clarify.md").read_text(
        encoding="utf-8")
    assert "`other_sessions`" in prompt and "`summary`" in prompt and "that chat" in prompt.lower()


def test_the_reader_recommends_and_asks_every_blocking_gap() -> None:
    """SR-223 EX-15: every gap that blocks is marked blocking and asked at once."""
    prompt = (Path(clarify.__file__).parent / "agents" / "clarify.md").read_text(
        encoding="utf-8")
    for words in ("Recommend whenever you can", "all of them are asked at once",
                  "`diagram`", "`proposal`", "consequences"):
        assert words in prompt, words
    assert "At most one gap" not in prompt and "spec session instead" not in prompt
    assert {"proposal"} <= set(clarify.schema["properties"]["readback"]["properties"])
    gap = clarify.schema["properties"]["gaps"]["items"]["properties"]
    assert {"consequences", "blocking", "diagram"} <= set(gap)
    assert "replaces" not in clarify.schema["properties"] and "open_cards" not in clarify.__doc__
