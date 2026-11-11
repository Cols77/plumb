"""SR-430 with DEC-542: owner-facing text never prints the old name."""

import re
from pathlib import Path

import pytest

from tests.rename.test_rename_iaso import ROOT, _run

OLD = re.compile("plum" + "b", re.I)  # also matches the folder
DOCS = ["docs/concept.md", "docs/hosts.md", "docs/browser-api.md", "docs/fork-plan.md",
        "docs/hermes-compat-implementation.md", "docs/hermes-compat-next-plan.md",
        "docs/hermes-compat-runtime-evidence.md", "plugin/README.md"]


def _commands(tmp_path: Path) -> list[str]:
    top = _run("iaso", ["--help"], tmp_path).stdout
    return sorted(set(re.findall(r"^  ([a-z][a-z-]+)\s{2,}", top, re.M)))


@pytest.mark.sr("SR-430")
def test_every_subcommand_help_names_no_old_name(tmp_path: Path) -> None:
    cmds = _commands(tmp_path)
    assert len(cmds) > 20
    bad = [c for c in cmds if OLD.search(_run("iaso", [c, "--help"], tmp_path).stdout)]
    assert not bad, f"help still names the old name: {bad}"


@pytest.mark.sr("SR-430")
@pytest.mark.parametrize("rel", DOCS)
def test_docs_name_no_old_name(rel: str) -> None:
    hits = OLD.findall((ROOT / rel).read_text(encoding="utf-8"))
    assert not hits, f"{rel}: {len(hits)} mentions of the old name"


@pytest.mark.sr("SR-430")
def test_plugin_skills_name_no_old_name() -> None:
    bad = [str(p.relative_to(ROOT)) for p in (ROOT / "plugin/skills").glob("iaso-*/**/*.md")
           if OLD.search(p.read_text(encoding="utf-8"))]
    assert not bad, bad


@pytest.mark.sr("SR-430")
def test_ui_names_no_old_name() -> None:
    assert not OLD.search((ROOT / "ui/package-lock.json").read_text(encoding="utf-8")[:400])
    assert "." + "plum" + "b-mark" not in (ROOT / "ui/src/app.css").read_text(encoding="utf-8")


@pytest.mark.sr("SR-430")
@pytest.mark.parametrize("rel", ["validate.py", "judgment/__init__.py", "approvals.py"])
def test_source_messages_name_no_old_folder(rel: str) -> None:
    text = (ROOT / "src/iaso" / rel).read_text(encoding="utf-8")
    msgs = [ln for ln in text.splitlines()
            if "." + "plum" + "b" in ln and not ln.lstrip().startswith("#")
            and re.search(r"""["'][^"']*\.""" + "plum" + "b", ln)]
    assert not msgs, msgs
