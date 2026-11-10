"""``iaso understand eval [--fake]``: run each case of ``evalset/{read,judge,clarify}.json``
on the configured dispatcher and write an ``eval-run`` entry (model, prompt digest = digest
of ``agents/*.md`` and ``schemas/*.json``, cases, passed, the clarifier's false-gap rate)."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from iaso.contracts import DispatchError, Job, NoModel

HERE = Path(__file__).resolve().parent
KINDS = ("read", "judge", "clarify")


def load_cases(kind: str) -> list[Mapping[str, Any]]:
    try:
        data = json.loads((HERE / "evalset" / f"{kind}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [c for c in data if isinstance(c, Mapping)] if isinstance(data, list) else []


def prompt_digest() -> str:
    digest = hashlib.sha256()
    for sub, pattern in (("agents", "*.md"), ("schemas", "*.json")):
        for path in sorted((HERE / sub).glob(pattern)):
            digest.update(path.name.encode("utf-8") + b"\0" + path.read_bytes() + b"\0")
    return "sha256:" + digest.hexdigest()


class FakeEvalDispatcher:
    """Answers every case with its own ``expect`` (``--fake``: the harness without a model)."""

    name = "fake"

    def available(self) -> str | None:
        return None

    def run(self, job: Job, *, system: str, user: str, schema: Mapping[str, Any],
            on_step: Any) -> Mapping[str, Any]:
        return dict(job.inputs.get("expect") or {})


def _answers_match(kind: str, answer: Mapping[str, Any], expect: Mapping[str, Any]) -> bool:
    """Whether a model's answer meets a frozen case, the way that kind reads its answer."""
    if kind == "judge":
        from iaso.understand import judge

        return judge.matches(answer, expect)
    if kind == "read":
        got = {str(e.get("id")): e for e in answer.get("entries") or () if isinstance(e, Mapping)}
        wanted = {str(e.get("id")): e for e in expect.get("entries") or ()}
        for name, item in wanted.items():
            if name not in got or got[name].get("answer") != item.get("answer"):
                return False
        # a confirmation nobody asked for is the worst mistake a reader can make
        return not any(e.get("answer") == "accepted" and name not in wanted
                       for name, e in got.items())
    return all(answer.get(k) == v for k, v in expect.items())


def _says_none(answer: Mapping[str, Any], never: Sequence[str]) -> bool:
    """Whether ``answer`` (as JSON, any case) contains none of a case's ``never_says``: a fact
    the reader must not state, such as a claim about the repository its inputs never gave."""
    text = json.dumps(answer, ensure_ascii=False).lower()
    return not any(str(phrase).lower() in text for phrase in never)


def _says_all(answer: Mapping[str, Any], groups: Sequence[Any]) -> bool:
    """Whether ``answer`` (as JSON, any case) says each of a case's ``says_any`` groups: one of
    the phrases of every group (a group may be a single phrase), so a reader that resolved a
    reference names what it points to, in whatever words."""
    text = json.dumps(answer, ensure_ascii=False).lower()
    for group in groups:
        phrases = [group] if isinstance(group, str) else list(group)
        if not any(str(phrase).lower() in text for phrase in phrases):
            return False
    return True


def _real_answer(dispatcher: Any, job: Job, kind: str) -> Mapping[str, Any]:
    """What the worker would send for ``job``: the kind's agent prompt, its inputs as the user
    message, its schema; an answer that fails the schema is an error, never a reading."""
    from iaso.understand import agents
    from iaso.understand import schema as schema_check
    from iaso.understand.kinds import KINDS

    module = KINDS[kind]
    answer = dict(dispatcher.run(
        job, system=agents.load(kind),
        user=json.dumps(job.inputs, ensure_ascii=False, sort_keys=True, indent=1),
        schema=module.schema, on_step=lambda step: None))
    found = schema_check.problems(answer, module.schema)
    if found:
        raise DispatchError("schema", "; ".join(found[:3]))
    return answer


def run_cases(dispatcher: Any, cases: Sequence[Mapping[str, Any]],
              kind: str) -> list[dict[str, Any]]:
    """Run each case. The fake dispatcher is handed the expected answer inside the inputs (the
    harness without a model); any other dispatcher gets the real prompt, inputs and schema, and
    never sees the expectation."""
    fake = isinstance(dispatcher, FakeEvalDispatcher)
    results: list[dict[str, Any]] = []
    for n, case in enumerate(cases):
        expect = dict(case.get("expect") or {})
        inputs = dict(case.get("inputs") or {})
        job = Job(id=f"eval-{kind}-{n}", kind=kind, schema=f"{kind}.v1",
                  inputs={**inputs, "expect": expect} if fake else inputs)
        error = ""
        try:
            if fake:
                answer = dict(dispatcher.run(job, system="", user=json.dumps(job.inputs),
                                             schema={}, on_step=lambda step: None))
                passed = all(answer.get(k) == v for k, v in expect.items())
            else:
                try:
                    answer = dict(_real_answer(dispatcher, job, kind))
                except KeyError:                 # a kind with no module: the plain protocol
                    answer = dict(dispatcher.run(job, system="", user=json.dumps(inputs),
                                                 schema={}, on_step=lambda step: None))
                passed = _answers_match(kind, answer, expect) and _says_none(
                    answer, case.get("never_says") or ()) and _says_all(
                    answer, case.get("says_any") or ())
            false_gap = bool(answer.get("gap")) and not expect.get("gap")
        except DispatchError as exc:
            passed, false_gap, error = False, False, f"{exc.step}: {exc.message}"
        row = {"kind": kind, "case": case.get("name", str(n)), "passed": passed,
               "false_gap": false_gap}
        if error:
            row["error"] = error
        results.append(row)
    return results


def run(command: str, argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="iaso understand eval")
    parser.add_argument("--fake", action="store_true")
    parser.add_argument("--root", default=None)
    parser.add_argument("--compare", default=None,
                        help="judges side by side on the labelled set, e.g. haiku,jev")
    parser.add_argument("--repin", action="store_true",
                        help="with --compare: the repin meaning judges on the repin set, "
                             "e.g. sonnet,haiku,sonnet-x3,jev")
    parser.add_argument("--set", dest="set_path", default=None)
    args = parser.parse_args(argv)
    from iaso.api import open_core
    from iaso.paths import find_root

    if args.repin and not args.compare:
        print("iaso: eval --repin needs --compare <judges>, e.g. sonnet,haiku,sonnet-x3,jev",
              file=sys.stderr)
        return 2
    core = open_core(find_root(Path(args.root or ".")))
    if args.repin:
        from iaso.understand import evalcompare, evalrepin

        names = [n.strip().lower() for n in args.compare.split(",") if n.strip()]
        try:
            print(evalrepin.run_compare(core, names, args.set_path))
        except evalcompare.CompareError as exc:
            print(f"iaso: eval --repin --compare: {exc}", file=sys.stderr)
            return 2
        return 0
    if args.compare:
        from iaso.understand import evalcompare

        names = [n.strip().lower() for n in args.compare.split(",") if n.strip()]
        try:
            print(evalcompare.run_compare(core, names, args.set_path))
        except evalcompare.CompareError as exc:
            print(f"iaso: eval --compare: {exc}", file=sys.stderr)
            return 2
        return 0
    judge_model = str(core.config.understand.judge_model)    # SR-186: verdicts follow it
    dispatchers: dict[str, Any] = {}
    for kind in KINDS:
        if args.fake:
            dispatchers[kind] = FakeEvalDispatcher()
            continue
        from iaso.understand.dispatch import configured

        try:
            dispatchers[kind] = configured(core, model=judge_model if kind == "judge" else None)
        except NoModel as exc:
            print(f"iaso: {exc}", file=sys.stderr)
            return 2
    cases = [r for kind in KINDS for r in run_cases(dispatchers[kind], load_cases(kind), kind)]
    clarify = [r for r in cases if r["kind"] == "clarify"]
    rate = (sum(r["false_gap"] for r in clarify) / len(clarify)) if clarify else 0.0
    passed = sum(1 for r in cases if r["passed"])
    core.log_append("events", "eval-run", {
        "model": "fake" if args.fake else judge_model,
        "prompt_digest": prompt_digest(), "cases": cases, "passed": passed,
        "false_gap_rate": rate})
    print(f"eval: {len(cases)} cases, {passed} passed")
    return 0
