"""A study written the way DEC-207 has it: the agent proposes the idea, the owner accepts it
at a depth (the band's press, ``study.choose``), then the agent writes it."""

from __future__ import annotations

from pathlib import Path

from iaso import study
from iaso.study import cli


def written(root: Path, session: str, title: str, why: str, body: Path,
            topic: str | None = None, depth: str = "diagrams") -> int:
    """``iaso study propose``, accepted at ``depth``, then ``iaso study add``: the first
    non-zero exit code, else 0."""
    common = ["--root", str(root), "--session", session]
    code = cli.run("study", ["propose", "--title", title, "--why", why, "--depth", "diagrams",
                             *(["--topic", topic] if topic else []), *common])
    if code:
        return code
    slug = next(s["slug"] for s in reversed(study.studies(root)) if s["status"] == "idea")
    study.choose(root, slug, depth)
    return cli.run("study", ["add", slug, "--file", str(body), "--records", *drawn(root, slug),
                             *common])


def drawn(root: Path, slug: str) -> list[str]:
    """The IDs ``iaso study gather`` finds on the study's topic (SR-360 EX-1, EX-3)."""
    from iaso.api import open_core

    return [r["id"] for r in cli.gather(open_core(root), root, slug)["records"]]
