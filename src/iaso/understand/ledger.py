"""The worker's ledger (ENGINE): ``ran/<job-id>`` holds one line (pid, time), written by the
worker only. A result that has no ledger entry was not written by the worker: it counts for
nothing and is reported."""

from __future__ import annotations

import os
import time
from pathlib import Path

from iaso.understand import files


def entry_path(root: Path, session: str, job_id: str) -> Path:
    return files.ran_dir(root, session) / job_id


def record(root: Path, session: str, job_id: str) -> None:
    path = entry_path(root, session, job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{os.getpid()} {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n",
                    encoding="utf-8")


def has(root: Path, session: str, job_id: str) -> bool:
    return entry_path(root, session, job_id).is_file()


def forget(root: Path, session: str, job_id: str) -> None:
    try:
        entry_path(root, session, job_id).unlink()
    except OSError:
        pass


def unledgered(root: Path, session: str) -> list[str]:
    """Ids with a result file but no ledger entry (a result nobody but the worker may write)."""
    folder = files.results_dir(root, session)
    if not folder.is_dir():
        return []
    return sorted(p.stem for p in folder.glob("*.json") if not has(root, session, p.stem))
