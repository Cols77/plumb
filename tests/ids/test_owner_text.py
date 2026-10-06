"""IDS owner-visible text names no shell command (sp6 11.1, R14): one test per surface, each
rendering the surface for real and asserting ``bare_cli_verbs(output) == []``; plus the
``bare_cli_verbs`` checker itself and every IDS constant."""

from __future__ import annotations

from pathlib import Path

import pytest

from ids import scenario
from ids.gitrepo import make_repo, write
from plumb.cli import main
from plumb.present import owner_text
from plumb.present.owner_text import bare_cli_verbs


@pytest.mark.sr("SR-070")
def test_bare_cli_verbs_flags_plumb_verbs() -> None:
    assert bare_cli_verbs("run plumb merge-fix now") == ["plumb merge-fix"]
    assert bare_cli_verbs("uv run plumb log migrate") == ["plumb log"]
    assert bare_cli_verbs("then plumb approve SR-001") == ["plumb approve"]


@pytest.mark.sr("SR-070")
def test_slash_command_passes() -> None:
    assert bare_cli_verbs("say /plumb merge-fix, or /plumb status") == []


@pytest.mark.sr("SR-070")
def test_plumb_colon_prefix_passes() -> None:
    assert bare_cli_verbs('plumb: SR-005 "relay checks" is also changed') == []
    assert bare_cli_verbs("plumb log: not available in this build") == []


IDS_CONSTANTS = ("ID_UNRESERVED", "ID_BUSY", "RENUMBERED", "APPROVAL_CARRIED",
                 "APPROVAL_NONE", "COLLISION", "COLLISIONS_HEADER", "NOTHING_TO_FIX",
                 "WOULD_RENUMBER", "FIX_REMAINS", "PREVIEW", "CARRIED", "CARRIED_GLANCE")


@pytest.mark.sr("SR-070")
def test_every_ids_constant_passes() -> None:
    for name in IDS_CONSTANTS:
        assert bare_cli_verbs(getattr(owner_text, name)) == [], name


@pytest.mark.sr("SR-070")
def test_fallback_line(tmp_path: Path, capsys) -> None:
    from plumb.commands import init_repo

    root = tmp_path / "plain"
    root.mkdir()
    init_repo(root)
    assert main(["new", "requirement", "--title", "t", "--root", str(root)]) == 0
    err = capsys.readouterr().err
    assert "is not reserved" in err and bare_cli_verbs(err) == []


@pytest.mark.sr("SR-070")
def test_busy_error(tmp_path: Path, monkeypatch, capsys) -> None:
    from plumb.ids import ref as ref_mod
    from plumb.ids import reservation

    root = make_repo(tmp_path / "r")
    monkeypatch.setattr(reservation, "RETRY_S", 0.1)

    def moved(*args, **kwargs):
        raise ref_mod.Moved("moved")

    monkeypatch.setattr(ref_mod, "update", moved)
    assert main(["new", "requirement", "--title", "t", "--root", str(root)]) == 2
    err = capsys.readouterr().err
    assert "could not reserve an ID" in err and bare_cli_verbs(err) == []


@pytest.mark.sr("SR-071")
def test_merge_fix_output(tmp_path: Path, capsys) -> None:
    s = scenario.build(tmp_path)
    outputs = []
    for argv in (["merge-fix", "--dry-run"], ["merge-fix"], ["merge-fix"]):
        main([*argv, "--root", str(s.origin)])
        outputs.append(capsys.readouterr().out)
    assert "would become" in outputs[0] and "is now" in outputs[1]
    assert "nothing to fix" in outputs[2]
    for out in outputs:
        assert bare_cli_verbs(out) == [], out


@pytest.mark.sr("SR-071")
def test_carried_label_surfaces(tmp_path: Path, capsys) -> None:
    from plumb.api import open_core
    from plumb.boundary.glance import glance_line, glance_rows

    s = scenario.build(tmp_path)
    main(["merge-fix", "--root", str(s.origin)])
    capsys.readouterr()
    main(["show", "SR-003", "--root", str(s.origin)])
    header = capsys.readouterr().out.splitlines()[0]
    assert "carried by renumber" in header and bare_cli_verbs(header) == []
    rows = [r for r in glance_rows(open_core(s.origin), set()) if r["kind"] == "renumber"]
    line = glance_line(rows[0])
    assert "carried by renumber" in line and bare_cli_verbs(line) == []


@pytest.mark.sr("SR-072")
@pytest.mark.parametrize("command", [["check", "--merge", "main"],
                                     ["merge-check", "main", "--no-run"]])
def test_collision_section(tmp_path: Path, capsys, command) -> None:
    from plumb.boundary.report import collision_lines

    root = make_repo(tmp_path / "r")
    write(root, "SR-070", "relay checks")
    (root / ".plumb" / "requirements" / "SR-070-b.md").write_text(
        "---\nid: SR-070\ntitle: export csv\n---\n", encoding="utf-8")
    assert main([*command, "--root", str(root)]) == 1
    out = capsys.readouterr().out
    section = [line for line in out.splitlines()
               if "ID collisions" in line or "/plumb merge-fix" in line]
    assert len(section) == 2
    assert bare_cli_verbs("\n".join(section)) == []
    assert collision_lines([]) == []
