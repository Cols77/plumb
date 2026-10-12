"""K1: normalization, paths, config, contracts and the dispatcher."""

from __future__ import annotations

import dataclasses
import json
import re
import sys
import unicodedata
from pathlib import Path

import pytest

from plumb import cli
from plumb.config import load_config
from plumb.contracts import Link, Pin, Record, Target
from plumb.normalize import canonical_json, file_digest, normalize_text, sha256_bytes, sha256_text
from plumb.paths import PlumbPaths, find_root
from plumb.text import CHANGE_WORDS, overlap, terms

pytestmark = pytest.mark.sr("SR-002")


def test_crlf_and_lone_cr_become_lf() -> None:
    assert normalize_text("a\r\nb\rc\n") == "a\nb\nc"
    assert sha256_text("a\r\nb") == sha256_text("a\nb")


def test_trailing_whitespace_and_blank_lines_dropped() -> None:
    assert normalize_text("a  \t\nb\n\n\n  \n") == "a\nb"


def test_nfc_normalization() -> None:
    decomposed = unicodedata.normalize("NFD", "café")
    assert decomposed != "café"
    assert normalize_text(decomposed) == "café"


def test_derived_blocks_removed() -> None:
    text = "keep\n<!-- derived -->\ngenerated\n<!-- end derived -->\nalso keep\n"
    assert normalize_text(text) == "keep\nalso keep"


def test_canonical_json_sorted_compact_utf8() -> None:
    assert canonical_json({"b": 1, "a": "é"}) == '{"a":"é","b":1}'.encode()
    assert sha256_bytes(b"x").startswith("sha256:")
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", sha256_bytes(b"x"))


def test_file_digest_binary_uses_raw_bytes(tmp_path: Path) -> None:
    binary = tmp_path / "b.bin"
    binary.write_bytes(b"\xff\xfe\x00\r\n")
    assert file_digest(binary) == sha256_bytes(b"\xff\xfe\x00\r\n")
    text = tmp_path / "t.txt"
    text.write_bytes(b"line \r\n")
    assert file_digest(text) == sha256_text("line")


def test_find_root_prefers_plumb_dir(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    inner = tmp_path / "pkg"
    (inner / ".plumb").mkdir(parents=True)
    deep = inner / "a" / "b"
    deep.mkdir(parents=True)
    assert find_root(deep) == inner.resolve()
    other = tmp_path / "other" / "x"
    other.mkdir(parents=True)
    assert find_root(other) == tmp_path.resolve()


def test_config_defaults_without_file(tmp_path: Path) -> None:
    config = load_config(tmp_path)
    assert config.verify.turn_budget_s == 15
    assert config.verify.hard_limit_factor == 1.5
    assert config.hooks.brief_lines == 30
    assert "ok" in config.approve.affirmations
    assert config.judgment.backend == ""  # no judge configured: judging raises (INT-029)
    assert config.source_dirs == ("src", "tests")


def test_config_yaml_overrides_and_cache(tmp_path: Path) -> None:
    (tmp_path / ".plumb").mkdir()
    (tmp_path / ".plumb" / "config.yaml").write_text(
        "verify:\n  turn_budget_s: 5\n  infra_globs: [uv.lock, x.py]\n", encoding="utf-8")
    config = load_config(tmp_path)
    assert config.verify.turn_budget_s == 5
    assert config.verify.infra_globs == ("uv.lock", "x.py")
    assert config.verify.sample_size == 10
    assert (tmp_path / ".plumb" / "cache" / "config.json").exists()
    assert load_config(tmp_path) == config


def test_paths_attributes(tmp_path: Path) -> None:
    paths = PlumbPaths(tmp_path)
    assert paths.log_events == tmp_path / ".plumb" / "log" / "events.jsonl"
    assert paths.prompts == tmp_path / ".plumb" / "session" / "prompts.jsonl"
    assert paths.session_dir("s1") == tmp_path / ".plumb" / "session" / "s1"
    for name in ("plumb", "config", "claims", "log_evidence", "cache", "session",
                 "test_map_txt", "test_map_json", "index_cache", "hash_cache",
                 "evidence_index", "env_identity", "lock", "status", "stated",
                 "escalations", "errors"):
        assert isinstance(getattr(paths, name), Path)


def test_dataclasses_are_frozen() -> None:
    pin = Pin("sha256:a", "sha256:b")
    with pytest.raises(dataclasses.FrozenInstanceError):
        pin.source = "x"  # type: ignore[misc]
    link = Link(source="SR-001", index=2, kind="derives_from", target=Target(record="INT-001"))
    assert link.id == "SR-001#2"
    record = Record(id="SR-001", kind="requirement", title="t", path="p", fields={}, body="",
                    links=())
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.title = "x"  # type: ignore[misc]


def test_text_terms_and_overlap() -> None:
    assert terms("The Links pin both ends") == frozenset({"links", "pin", "both", "ends"})
    assert overlap(frozenset(), frozenset({"a"})) == 0
    assert overlap(frozenset({"links", "pin"}), frozenset({"links", "pin", "ends", "both"})) == 1
    assert "instead" in CHANGE_WORDS


def test_unknown_command_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["no-such-command"]) == 2
    assert "unknown command" in capsys.readouterr().err


def test_missing_module_reports_not_available(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setitem(cli.ROUTES, "ghost", "plumb.no_such_lane.cli")
    assert cli.main(["ghost"]) == 2
    assert "plumb: 'ghost' is not available in this build" in capsys.readouterr().err


def test_every_route_names_a_module_path() -> None:
    expected = {"init", "new", "show", "link", "repin", "validate", "check", "status", "drift",
                "brief", "explain", "why", "approve", "relay", "revoke", "tests", "map",
                "verify", "impact", "hook", "hooks", "install", "statusline", "trailers",
                "claims", "import", "fidelity", "judge", "judgment",
                # sub-projects 2 to 5 (next-plan 3.2 item 4)
                "capture", "intent", "example", "decide", "escalate", "spec", "triage",
                "config", "jev", "clarify", "merge-check", "hosts", "turn", "mcp", "resolve",
                "review", "confirm", "align", "view",
                # sub-project 6 (sp6 plan 3.2 item 5)
                "log", "merge-fix", "ids", "merge-driver", "conflict", "conflicts",
                "inflight",
                # SR-127: a requirement's proof plan and evidence
                "proof",
                # sub-project 8 (understanding layer, phase C stubs)
                "understand", "go", "settle", "undo",
                # sp8 STALE: `plumb stale card`
                "stale",
                # sub-project 7 PLUGIN: `plumb plugin ignore|unignore|migrate`
                "plugin",
                # sp7 slice 4: the panel's own commands (not advertised in --help)
                "mod"}
    assert set(cli.ROUTES) == expected
    for module in cli.ROUTES.values():
        assert re.fullmatch(r"plumb(\.[a-z_]+)+", module)


def test_help_lists_commands(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--help"]) == 0
    out = capsys.readouterr().out
    assert "usage: plumb" in out
    assert "validate" in out


def test_entry_point_imports_stay_light() -> None:
    import subprocess

    code = ("import sys; from plumb import cli; "
            "print(json.dumps(sorted(m for m in ('yaml','argparse','subprocess','ast') "
            "if m in sys.modules)))")
    out = subprocess.run([sys.executable, "-c", "import json; " + code], capture_output=True,
                         text=True, check=True).stdout
    assert json.loads(out) == []


def test_plumbs_own_home_is_never_taken_for_a_repository(tmp_path: Path) -> None:
    """~/.plumb holds the plugin's environments (env/, current.json): a folder under the
    user's home walks past it, even when records were once written there by mistake."""
    from plumb.paths import holds_records

    home = tmp_path / "home"
    (home / ".plumb" / "env").mkdir(parents=True)
    (home / ".plumb" / "requirements").mkdir()             # left there by an earlier mistake
    (home / ".plumb" / "config.yaml").write_text("{}\n", encoding="utf-8")
    work = home / "scratch" / "x"
    work.mkdir(parents=True)
    assert holds_records(home) is False
    assert find_root(work) == work.resolve()
    (work / ".plumb").mkdir()                              # a repository's own records count
    assert holds_records(work) is True and find_root(work) == work.resolve()
