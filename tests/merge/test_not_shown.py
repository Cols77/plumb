"""SR-127 EX-3 (DEC-037): merge-check names the branch's requirements whose proof was not
shown working, as information; it never holds the merge."""

from __future__ import annotations

from pathlib import Path

import pytest
from merge_helpers import INT, SR2, commit, repin_all, write

from iaso import cli
from iaso.api import open_core
from iaso.boundary import exit_code, merge_report, render
from iaso.capture.proof import set_evidence, set_plan
from iaso.contracts import Target

pytestmark = pytest.mark.sr("SR-253")

SR1 = "---\nid: SR-001\ntitle: Links pin both ends\nstatement: Both ends are pinned.\n---\n"


@pytest.fixture
def base(repo: Path) -> tuple[Path, str]:
    write(repo, ".iaso/intents/INT-001.md", INT)
    write(repo, ".iaso/requirements/SR-001.md", SR1)
    write(repo, ".iaso/requirements/SR-002.md", SR2)
    write(repo, "src/mod.py", "x = 1\n")
    core = open_core(repo)
    core.add_link("SR-001", "derives_from", Target(record="INT-001"))
    core.add_link("SR-001", "implemented_by", Target(path="src/mod.py"))
    core.add_link("SR-002", "derives_from", Target(record="INT-001"))
    return repo, commit(repo, "base")


def test_never_shown_is_named_and_does_not_change_the_exit(base) -> None:
    root, sha = base
    write(root, "src/mod.py", "x = 2\n")
    repin_all(root)
    commit(root, "change mod\n\nSR: SR-001")
    report = merge_report(open_core(root), sha, run_full=False)
    assert [r["id"] for r in report.not_shown] == ["SR-001"]
    assert report.not_shown[0]["why"] == "no proof"
    text = "\n".join(render(report))
    assert "not shown working yet (information; a proof holds only work landing on the " \
           "default branch that delivers it):" in text
    assert "SR-001 Links pin both ends: no proof planned (iaso show SR-001)" in text
    # the same report without the section exits the same: it never holds
    from dataclasses import replace

    assert exit_code(report) == exit_code(replace(report, not_shown=()))


def test_shown_working_is_not_named(base, capsys) -> None:
    root, sha = base
    write(root, "src/mod.py", "x = 2\n")
    repin_all(root)
    core = open_core(root)
    set_plan(core, "SR-001", "run iaso show SR-001", "command")
    commit(root, "change mod\n\nSR: SR-001")
    report = merge_report(open_core(root), sha, run_full=False)
    assert [(r["id"], r["why"]) for r in report.not_shown] == [("SR-001", "not run")]
    set_evidence(open_core(root), "SR-001", "https://x.test/run", "printed", passed=False)
    report = merge_report(open_core(root), sha, run_full=False)
    assert [(r["id"], r["why"]) for r in report.not_shown] == [("SR-001", "failed")]
    set_evidence(open_core(root), "SR-001", "https://x.test/run", "printed", passed=True)
    report = merge_report(open_core(root), sha, run_full=False)
    assert report.not_shown == ()
    assert "shown working: every touched requirement" in render(report)
    assert cli.main(["merge-check", sha, "--no-run", "--json", "--root", str(root)]) in (0, 4, 5)
    assert '"not_shown": []' in capsys.readouterr().out
