"""IS1: the claims policy and the ingest checkpoint (concept 10, next-plan 9.1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from importer_helpers import make_source, plumb_files, write

from plumb.api import open_core
from plumb.claims import load_policy
from plumb.importer.pi_factory import import_pi_factory

pytestmark = pytest.mark.sr("SR-058")

POLICY = """# Commit-claim traceability config (SR-049).
epoch: "0f6576309598f232600fef2f5bceeb6279f23fa8"
exempt:
  - "docs/**"
  - "evidence/**"
  - "bundles/**"
baseline_size: 2
baseline:
  - {sr: SR-034, path: ".gitignore", nc: NC-0011}
  - {sr: SR-076, path: "tests/unit/coherence/test_contract_cli.py", nc: NC-0011}
"""


def _ingest(sha: str, sr_ids: list[str], files: list[str], result: str) -> str:
    return json.dumps({"schema_version": 2, "outcome": "completed", "result_commit": result,
                       "commits": [{"sha": sha, "subject": "s", "sr_ids": sr_ids,
                                    "changed_files": files, "exempted": []}]})


@pytest.fixture
def source(tmp_path: Path) -> Path:
    source = make_source(tmp_path)
    write(source, ".factory/trace-claims.yaml", POLICY)
    write(source, "evidence/runs/ingest-20261001T000000Z.json",
          _ingest("a" * 40, ["SR-034"], [".gitignore", "src/x.py"], "c" * 40))
    write(source, "evidence/runs/ingest-20261002T000000Z.json",
          _ingest("b" * 40, ["SR-077"], ["src/y.py"], "d" * 40))
    return source


def test_policy_and_checkpoint_imported_once(repo: Path, source: Path) -> None:
    report = import_pi_factory(open_core(repo), source)
    policy = load_policy(repo)
    assert not policy.problems
    assert {"evidence/**", "bundles/**"} <= set(policy.exempt)
    assert [(b.commit, b.path, b.nc) for b in policy.baseline] == [
        ("a" * 40, ".gitignore", "NC-0011")]
    data = yaml.safe_load((repo / ".plumb" / "claims.yaml").read_text(encoding="utf-8"))
    assert data["require_trailer"] is True and data["epoch"].startswith("0f6576")
    assert any(f["kind"] == "baseline-unmapped" and f["id"] == "SR-076"
               for f in report["findings"])
    [ingest] = [e for e in open_core(repo).log_read("events") if e.kind == "claims-ingest"]
    assert ingest.payload["checkpoint"] == "d" * 40
    assert [c["sha"] for c in ingest.payload["commits"]] == ["a" * 40, "b" * 40]
    assert ingest.payload["commits"][0] == {"sha": "a" * 40, "sr_ids": ["SR-034"],
                                            "paths": [".gitignore", "src/x.py"]}
    # the same source again: nothing rewritten, no second checkpoint
    before = plumb_files(repo)
    import_pi_factory(open_core(repo), source)
    assert plumb_files(repo) == before


def test_only_claims_and_dry_run(repo: Path, source: Path) -> None:
    before = plumb_files(repo)
    report = import_pi_factory(open_core(repo), source, only={"CLAIMS"}, dry_run=True)
    assert any(line.startswith("update .plumb/claims.yaml") or
               line.startswith("create .plumb/claims.yaml") for line in report["diff"])
    assert any(line.startswith("claims-ingest: 2") for line in report["diff"])
    assert plumb_files(repo) == before
    import_pi_factory(open_core(repo), source, only={"CLAIMS"})
    assert open_core(repo).index() == {}
    kinds = [e.kind for e in open_core(repo).log_read("events")]
    assert kinds == ["claims-ingest", "import"]
