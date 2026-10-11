"""SP7 slice 3: cards only at the end of a turn (SR-012, SR-113 EX-2, SR-116; sp7-realign-sp8
C1, C7, C8). The stop hook's owner text is what the owner's words confirmed, the settled line,
then every card in full; never a list of proposed records, never a status card."""

from __future__ import annotations

import io
import json
import subprocess
import time
from pathlib import Path

import pytest
from fakes import FakeVerify

from plumb import stale
from plumb.api import open_core
from plumb.contracts import NodeEvidence, Target
from plumb.hosts.claude_code import stop
from plumb.present import owner_text

pytestmark = pytest.mark.sr("SR-012")

SESSION = "s1"
NODE = "tests/test_a.py::test_a"
QUOTE = "the calculator adds"
PROMPT = "please make sure the calculator adds two numbers, nothing fancy"
PROMPT_DIGEST = "sha256:" + "c5" * 32
INT1 = f"""---
id: INT-001
title: Arithmetic helpers
quote: "{QUOTE}"
readback: The calculator adds two numbers.
prompt: {PROMPT_DIGEST[7:23]}
---
"""
FEAT1 = """---
id: FEAT-001
title: Merge check
---
"""
SR1 = """---
id: SR-001
title: Adds numbers
feature: FEAT-001
statement: add returns the sum.
examples:
- id: EX-1
  given: 1 and 2
  when: add runs
  then: it returns 3
---
"""
CODE = "def add(a, b):\n    return a + b\n"


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _log_prompt(repo: Path, text: str = PROMPT, digest: str = PROMPT_DIGEST,
                at: str = "2026-10-01T10:00:00Z") -> None:
    prompts = Path(open_core(repo).paths.prompts)
    prompts.parent.mkdir(parents=True, exist_ok=True)
    with prompts.open("a", encoding="utf-8") as out:
        out.write(json.dumps({"digest": digest, "session": SESSION, "at": at, "text": text,
                              "via": "hook"}) + "\n")


@pytest.fixture
def project(repo: Path, write_record, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(repo)
    write_record(repo, INT1)
    write_record(repo, FEAT1)
    write_record(repo, SR1)
    (repo / "src").mkdir()
    (repo / "src" / "calc.py").write_text(CODE, "utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_a.py").write_text("def test_a():\n    assert True\n", "utf-8")
    core = open_core(repo)
    core.add_link("SR-001", "derives_from", Target(record="INT-001"))
    core.add_link("SR-001", "implemented_by", Target(path="src/calc.py"))
    core.add_link("SR-001", "verified_by", Target(test=NODE))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "setup")
    _log_prompt(repo)
    return repo


def start_turn(repo: Path) -> None:
    path = repo / ".plumb" / "session" / SESSION / "turn.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"turn_start": time.time() - 0.5,
                                "prompt_digest": "sha256:" + "a" * 64, "asked": {}}), "utf-8")


def edit(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, "utf-8")
    with (repo / ".plumb" / "session" / SESSION / "touched.txt").open("a",
                                                                       encoding="utf-8") as f:
        f.write(rel + "\n")


def run_stop(repo: Path, hook_input, *, verify=None, active: bool = False) -> str:
    out = io.StringIO()
    payload = hook_input("Stop", session_id=SESSION, stop_hook_active=active)
    assert stop.main(stdin=io.StringIO(payload), stdout=out, root=repo,
                     verify=verify if verify is not None else FakeVerify(), unjudged=None) == 0
    return out.getvalue()


def owner(out: str) -> str:
    data = json.loads(out) if out.strip() else {}
    assert data.get("decision") != "block", data
    return data.get("systemMessage", "")


def heads(text: str) -> list[str]:
    """The first line of each card: a line that does not start with a space."""
    return [line for line in text.splitlines() if line and not line.startswith(" ")]


def no_list_summary(text: str) -> None:
    """SR-012: no list-style alignment summary, no status card, no summary lines."""
    for banned in ("▸", 'say "ok" to confirm', "plumb: touched", "questions:", "plumb ✓",
                   "plumb ✗", "plumb show"):
        assert banned not in text, banned


def owner_level(text: str) -> list[str]:
    from understand.fakes import owner_level as scan

    return scan(text)


# --------------------------------------------------------------------------- SR-012


def _settle_all(repo: Path, ids: list[str]) -> None:
    from understand.fakes import as_worker
    from understand.test_settle import judged, settling_on

    settling_on(open_core(repo))
    _, applied = judged(open_core(repo), ids, [0.95] * len(ids))
    core = open_core(repo)
    with as_worker(repo, SESSION):
        for entry in applied.entries:
            core.log_append("events", entry["kind"], entry["payload"])


def test_ex1_a_settled_record_shows_only_in_the_settled_line(repo: Path, write_record,
                                                             hook_input, monkeypatch) -> None:
    """EX-1: a turn proposed a requirement the judge settled, touching nothing confirmed: it
    shows only in the settled line with Undo, and no card."""
    from understand.test_settle import make_world

    monkeypatch.chdir(repo)
    ids = make_world(repo, write_record, 1)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "world")
    time.sleep(0.6)                         # the world predates the turn
    start_turn(repo)
    path = repo / ".plumb" / "requirements" / "SR-001.md"
    edit(repo, ".plumb/requirements/SR-001.md", path.read_text("utf-8"))
    _settle_all(repo, ids)
    text = owner(run_stop(repo, hook_input))
    (line,) = text.splitlines()
    assert line.startswith("Settled from your words: Operation 1 (Undo)")
    no_list_summary(text)


def test_ex2_a_regression_is_a_card_naming_the_test_and_what_it_checks(project: Path,
                                                                       hook_input) -> None:
    """EX-2: a test that passed with recorded evidence now fails: a regression card naming
    the test, what it checks, the change, and the suggested resolutions."""
    start_turn(project)
    edit(project, "src/calc.py", "def add(a, b):\n    return a * b\n")
    verify = FakeVerify(nodes=(NODE,), evidence_map={NODE: NodeEvidence(
        NODE, "fresh-fail", regression=True, last_run="run-2")})
    first = json.loads(run_stop(project, hook_input, verify=verify))
    assert first["decision"] == "block"            # the agent is told first (trigger 3)
    text = owner(run_stop(project, hook_input, verify=verify, active=True))
    lines = text.splitlines()
    assert lines[0] == ('Something that worked now fails, "Adds numbers": a test that passed '
                        'before now fails: "Adds numbers"')
    assert f"  Evidence: {NODE} passed in an earlier run and fails now (last run run-2)" in lines
    assert "  As it now reads (Adds numbers): add returns the sum." in lines
    assert "    EX-1: given 1 and 2, when add runs, then it returns 3" in lines
    assert any(line.startswith("  What changed in src/calc.py") for line in lines)
    assert "    +    return a * b" in lines
    assert f'  Your words (Arithmetic helpers): "{QUOTE}"' in lines
    assert "  1. Fix the code so it passes again (recommended)" in lines
    assert "  2. The test is wrong now: change it (say how)" in lines
    assert "  3. Leave it failing for now" in lines
    assert lines.count("     does and leaves undone: " + owner_text.CONSEQUENCES[
        owner_text.REGRESSION_FIX]) == 1
    assert "  Why the recommended one: " + owner_text.WHY_RECOMMENDED["regression"] in lines
    no_list_summary(text)
    # the card stays open: the next turn end draws it again while the test still fails
    start_turn(project)
    edit(project, "docs/notes.md", "notes\n")
    again = owner(run_stop(project, hook_input, verify=FakeVerify()))
    assert again.startswith('Something that worked now fails, "Adds numbers"')


INT2 = """---
id: INT-002
title: Divide numbers
quote: add a divide function
readback: You want a divide function for two numbers.
will:
- add divide(a, b)
wont:
- handle complex numbers
assumptions:
- id: A-1
  text: "ASSUMPTION: division by zero raises ValueError"
---
"""


def test_ex3_an_unsettled_intent_is_a_card_with_its_read_back(project: Path,
                                                               hook_input) -> None:
    """EX-3: an intent captured this turn the judge could not settle: a card with what it
    says, what will and won't be done, its labelled assumptions and suggested resolutions,
    never only an ID or a line in a summary."""
    start_turn(project)
    edit(project, ".plumb/intents/INT-002.md", INT2)
    text = owner(run_stop(project, hook_input))
    lines = text.splitlines()
    assert lines[0] == ('Proposed this turn, "Divide numbers": this was written from your '
                        "words this turn and is not settled; is it right?")
    assert "  As it now reads (Divide numbers): You want a divide function for two numbers." \
        in lines
    assert "    will: add divide(a, b)" in lines
    assert "    won't: handle complex numbers" in lines
    assert "    assumed (A-1): ASSUMPTION: division by zero raises ValueError" in lines
    assert '  Your words (Divide numbers): "add a divide function"' in lines
    assert [line for line in lines if line[:5] in ("  1. ", "  2. ", "  3. ")] == [
        "  1. Yes, as they read (recommended)", "  2. Yes, except the ones I name (say how)",
        "  3. Not yet: leave them open"]
    assert all(lines[lines.index(o) + 1].startswith("     does and leaves undone: ")
               for o in lines if o[:5] in ("  1. ", "  2. ", "  3. "))
    assert owner_level(text) == []
    no_list_summary(text)


def test_ex4_twelve_requirements_of_one_feature_are_one_card(project: Path,
                                                             hook_input) -> None:
    """EX-4 (DEC-029): twelve requirements of one feature, none settled: one card for the
    feature, not a list of twelve lines."""
    start_turn(project)
    for n in range(10, 22):
        edit(project, f".plumb/requirements/SR-0{n}.md",
             f"---\nid: SR-0{n}\ntitle: Check {n}\nfeature: FEAT-001\nstatement: the merge check "
             f"does {n}.\nexamples:\n- id: EX-1\n  given: g{n}\n  when: w{n}\n  then: t{n}\n---\n")
    text = owner(run_stop(project, hook_input))
    assert heads(text) == ['Proposed this turn, "Merge check": these 12 were written from your '
                           "words this turn and are not settled; are they right?"]
    for n in range(10, 22):
        assert f"  - Check {n}" in text.splitlines()
        assert f"    the merge check does {n}." in text.splitlines()
    no_list_summary(text)
    stated = json.loads((project / ".plumb" / "session" / "stated.json").read_text("utf-8"))
    assert all(r["shown"] for r in stated["records"]) and len(stated["records"]) == 12


def test_ex5_nothing_for_the_owner_shows_nothing(project: Path, hook_input) -> None:
    """EX-5: nothing needs the owner and nothing settled: the hook shows the owner nothing."""
    start_turn(project)
    edit(project, "src/calc.py", "def add(a, b):\n    return b + a\n")
    verify = FakeVerify(nodes=(NODE,), evidence_map={NODE: NodeEvidence(NODE, "fresh-pass")})
    assert run_stop(project, hook_input, verify=verify) == ""


def test_a_proposed_record_confirmed_since_leaves_its_card(project: Path, hook_input) -> None:
    """The card of a turn's records stays open across turns, and a record confirmed since is
    no longer asked about (it is not shown as a card, SR-012 EX-1)."""
    from plumb import approvals

    start_turn(project)
    edit(project, ".plumb/intents/INT-002.md", INT2)
    assert owner(run_stop(project, hook_input)).startswith('Proposed this turn, "Divide')
    start_turn(project)
    edit(project, "docs/notes.md", "notes\n")
    assert owner(run_stop(project, hook_input)).startswith('Proposed this turn, "Divide')
    approvals.approve(open_core(project), ["INT-002"])
    start_turn(project)
    edit(project, "docs/notes.md", "more notes\n")
    assert run_stop(project, hook_input) == ""


# --------------------------------------------------------------------------- SR-113 EX-2

INT8 = """---
id: INT-008
title: Cards only at the end of a turn
quote: no list-style summary at the end of a turn, cards only
readback: The end of a turn shows cards only.
---
"""
SR12 = """---
id: SR-012
title: End-of-turn cards
statement: the end-of-turn hook prints no list-style summary of proposed records.
examples:
- id: EX-1
  given: a turn proposed a record
  when: the turn ends
  then: no list-style line names it
---
"""
STOP_CODE = "def summary():\n    return []\n"
STOP_LIST = "def summary():\n    return ['- SR-030 proposed, say ok to confirm']\n"
REQUEST = "add a short list of the proposed records at the end of each turn"


@pytest.mark.sr("SR-113")
def test_sr113_ex2_code_that_drifted_from_an_agreed_intent_is_a_drift_card(
        repo: Path, write_record, hook_input, monkeypatch) -> None:
    """SR-113 EX-2: INT-008 and SR-012 agree, and a turn the owner asked for adds a list-style
    summary to the end-of-turn hook: the owner gets a card naming the intent, the
    requirement, the change and the request behind it, with keep-and-reword or undo."""
    monkeypatch.chdir(repo)
    write_record(repo, INT8)
    write_record(repo, SR12)
    (repo / "src").mkdir()
    (repo / "src" / "stophook.py").write_text(STOP_CODE, "utf-8")
    core = open_core(repo)
    core.add_link("SR-012", "derives_from", Target(record="INT-008"))
    core.add_link("SR-012", "implemented_by", Target(path="src/stophook.py"))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "setup")
    _log_prompt(repo, REQUEST, "sha256:" + "d1" * 32, "2026-10-01T09:00:00Z")
    start_turn(repo)
    edit(repo, "src/stophook.py", STOP_LIST)
    link = next(f"SR-012#{n}" for n, item in enumerate(open_core(repo).index()["SR-012"].links)
                if item.kind == "implemented_by")
    stale.add_card(repo, SESSION, link=link, record="SR-012", path="src/stophook.py",
                   topic="End-of-turn cards",
                   issue="the end of a turn now lists the proposed records",
                   options=["Keep the change and reword the requirement", "Undo the change"],
                   recommended=1, by="diagnosis",
                   consequences=["the list stays and the requirement says so; cards-only is "
                                 "dropped", "the list goes; the turn's request is not done"],
                   why="your intent says cards only, and the requirement still agrees with it")
    text = owner(run_stop(repo, hook_input))
    lines = text.splitlines()
    assert lines[0] == ('The code moved away from what you asked, "End-of-turn cards": the end '
                        "of a turn now lists the proposed records")
    evidence = next(line for line in lines if line.startswith("  Evidence: "))
    assert 'your intent "Cards only at the end of a turn"' in evidence      # the intent
    assert f'the request behind the change: "{REQUEST}"' in evidence        # the request
    assert ("  As it now reads (End-of-turn cards): the end-of-turn hook prints no list-style "
            "summary of proposed records.") in lines                          # the requirement
    assert "    +    return ['- SR-030 proposed, say ok to confirm']" in lines  # the change
    assert "  1. Undo the change (recommended)" in lines
    assert "  2. Keep the change and reword the requirement" in lines
    assert "     does and leaves undone: the list goes; the turn's request is not done" in lines
    assert ("  Why the recommended one: your intent says cards only, and the requirement still "
            "agrees with it") in lines


# --------------------------------------------------------------------------- SR-116


@pytest.mark.sr("SR-116")
def test_sr116_ex1_a_stale_card_shows_everything_to_choose(project: Path,
                                                            hook_input) -> None:
    """EX-1: the end-of-turn text shows the requirement's current wording, the change itself,
    the owner's words it came from, each option's consequence and why the first."""
    start_turn(project)
    edit(project, "src/calc.py", "def add(a, b):\n    return a * b\n")
    link = next(f"SR-001#{n}" for n, item in enumerate(open_core(project).index()["SR-001"].links)
                if item.kind == "implemented_by")
    stale.add_card(project, SESSION, link=link, record="SR-001", path="src/calc.py",
                   topic="Adds numbers", issue="add now multiplies",
                   options=["Undo the change", "Keep it and reword the requirement"],
                   consequences=["add sums again; the multiplying is dropped",
                                 "add keeps multiplying and the requirement says so"],
                   why="your words ask for a sum")
    verify = FakeVerify(nodes=(NODE,), evidence_map={NODE: NodeEvidence(NODE, "fresh-pass")})
    text = owner(run_stop(project, hook_input, verify=verify))
    lines = text.splitlines()
    assert lines[0] == 'Something you confirmed may have changed, "Adds numbers": add now ' \
                       "multiplies"
    assert "  As it now reads (Adds numbers): add returns the sum." in lines
    assert "    -    return a + b" in lines and "    +    return a * b" in lines
    assert f'  Your words (Arithmetic helpers): "{QUOTE}"' in lines
    assert f'    from your message: "{PROMPT}"' in lines
    assert "  1. Undo the change (recommended)" in lines
    assert "     does and leaves undone: add sums again; the multiplying is dropped" in lines
    assert "  Why the recommended one: your words ask for a sum" in lines
    assert owner_level("\n".join(line for line in lines if not line.startswith("    "))) == []


@pytest.mark.sr("SR-116")
def test_sr116_ex2_a_long_diff_is_folded_with_its_size_never_cut(project: Path,
                                                                  hook_input) -> None:
    start_turn(project)
    body = "".join(f"    total = total + {n}  # step {n} of the long change\n"
                   for n in range(400))
    edit(project, "src/calc.py", "def add(a, b):\n    total = a + b\n" + body
         + "    return total\n")
    link = next(f"SR-001#{n}" for n, item in enumerate(open_core(project).index()["SR-001"].links)
                if item.kind == "implemented_by")
    stale.add_card(project, SESSION, link=link, record="SR-001", path="src/calc.py",
                   topic="Adds numbers", issue="add now sums many steps",
                   options=["Keep it", "Undo it"], consequences=["keeps it", "undoes it"],
                   why="it still sums")
    verify = FakeVerify(nodes=(NODE,), evidence_map={NODE: NodeEvidence(NODE, "fresh-pass")})
    text = owner(run_stop(project, hook_input, verify=verify))
    folded = next(line for line in text.splitlines() if line.startswith("    [folded: "))
    assert "characters" in folded and "open it to read it in full" in folded
    assert "step 399 of the long change" not in text
    from plumb.understand import fullcard

    (entry,) = stale.read_cards(project, SESSION)
    content = fullcard.stale_content(open_core(project), entry, session=SESSION)
    assert "step 399 of the long change" in content["change"]["diff"]     # kept whole
    assert content["change"]["folded"] is True


@pytest.mark.sr("SR-116")
def test_sr116_ex4_the_agent_is_told_cards_wait_never_to_restate_them(project: Path,
                                                                       hook_input) -> None:
    """EX-4 (text): the owner's text draws each card once, in full; the next prompt tells the
    agent in one line that cards are waiting and not to restate them or ask for prose."""
    from plumb.hosts.claude_code import prompt

    start_turn(project)
    edit(project, ".plumb/intents/INT-002.md", INT2)
    text = owner(run_stop(project, hook_input))
    assert text.count('Proposed this turn, "Divide numbers"') == 1
    no_list_summary(text)
    out = io.StringIO()
    payload = hook_input("UserPromptSubmit", session_id=SESSION, prompt="carry on please")
    assert prompt.main(stdin=io.StringIO(payload), stdout=out, root=project) == 0
    told = [line for line in out.getvalue().splitlines() if "cards were shown" in line]
    assert told == [owner_text.CARDS_WAITING_AGENT.format(n=1, topics='"Divide numbers"')]
    assert "do not restate them" in told[0]


@pytest.mark.sr("SR-116")
def test_every_card_kind_is_drawn_in_full(project: Path) -> None:
    """Each kind plumb builds carries the parts that apply to it: the record as it reads,
    the owner's words, every option with what it does, and why the first."""
    from plumb.awareness.early import EarlyConflict
    from plumb.contracts import IntentConflict
    from plumb.understand import cards, fullcard

    core = open_core(project)
    index = core.index()
    record = index["SR-001"]
    built = [
        cards.regression_card(index, NODE, last_run="r1"),
        cards.proposed_cards(index, ["SR-001"])[0],
        cards.conflict_card(index, IntentConflict(
            ic="IC-001", record="SR-001", title="Adds numbers",
            fields={"statement": {"base": "a", "ours": "add returns the sum.",
                                  "theirs": "add returns the total."}},
            labels=("main", "feat-x"))),
        cards.early_conflict_card(index, EarlyConflict(
            record="SR-001", title="Adds numbers", branch="feat-x", claim="CL-1",
            theirs="add returns the total", ours="add returns the sum")),
        cards.issue_card("beyond", record, "it promises more than you said", "you said: add",
                         (owner_text.BEYOND_KEEP, owner_text.BEYOND_DROP,
                          owner_text.BEYOND_REWORD)),
    ]
    for card in built:
        item = fullcard.content(core, card)
        text = fullcard.render(item)
        assert item["record_now"] is not None or item["items"], card.kind
        assert item["owner_words"]["items"], card.kind
        assert all(o["consequence"] for o in item["options"]), card.kind
        assert item["why"], card.kind
        assert owner_text.FULL_NOT_WRITTEN not in text, card.kind
        assert "(recommended)" in text.splitlines()[
            next(i for i, line in enumerate(text.splitlines()) if line.startswith("  1. "))]
        assert owner_level(text) == [], (card.kind, owner_level(text))
        json.dumps(item)                                   # plain data, for present.json


def test_what_every_option_does_is_at_the_owners_level() -> None:
    """The consequences and reasons are owner text: no bare commands, internals or IDs."""
    texts = [*owner_text.CONSEQUENCES.values(), *owner_text.WHY_RECOMMENDED.values(),
             *owner_text.CONSEQUENCE_PICK.values()]
    for text in texts:
        assert owner_level(text) == [], text
