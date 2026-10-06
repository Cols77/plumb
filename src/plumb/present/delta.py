"""The one emitter of agent-facing hook lines: a deduplicated delta within a token budget
(sp5 3, SR-063, ruling R9 context economy).

Every agent-facing line of the session-start, prompt and stop hooks (and so of the
host-neutral API, which delegates to them) goes through ``Emitter.add``:

- each line has a subject and a state (a record: ``record:SR-004`` with its hash and
  confirmation; an instruction: its own digest, or a subject the caller names, such as
  ``untraced:src/app/mul.py``); a line whose subject already reached the agent this session
  in the same state is dropped;
- the per-hook budget (``hooks.prompt_tokens`` for the prompt hook, ``hooks.stop_tokens``
  for the stop hook's instructions, 4 characters per token) bounds what one call injects; a
  record line cut by the budget is named with ``plumb show`` and is not marked seen, so a
  later turn brings it; ``must`` lines (the relay line, a trigger question, the covering
  tests instruction) are never cut, nor are ``oneshot`` lines: a line whose source the hook
  consumes when it reads it (the queued untraced-change instruction, a queued cascade
  escalation), so a cut would lose it for good;
- nothing is emitted when nothing is new.

The seen set lives in ``.plumb/session/<session>/seen.json`` and is written only when the
hook closes the emitter, so a hook cut short re-emits next time rather than losing a line.
``/clear`` and compaction delete it (the session-start hook). Standard library only.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CHARS_PER_TOKEN = 4
SEEN_FILE = "seen.json"
MORE_WIDTH = 200


@dataclass(frozen=True)
class Line:
    """One agent-facing line and what makes it new."""

    text: str
    subject: str | None = None     # what the line is about; None: the text itself
    state: str = ""                # the subject's state; the line returns when it changes
    record: str | None = None      # the record a cut line names with plumb show
    group: str | None = None       # lines sharing a header (printed before the first)
    must: bool = False             # never cut by the budget
    oneshot: bool = False          # its source is consumed once read: never cut either
    marks: tuple[str, ...] = ()    # further subjects marked seen with this line

    @property
    def kept(self) -> bool:
        """Never cut by the budget or the line cap: ``must`` or ``oneshot``."""
        return self.must or self.oneshot

    def key(self) -> tuple[str, str]:
        if self.subject:
            return self.subject, self.state or "-"
        digest = hashlib.sha256(self.text.encode("utf-8")).hexdigest()[:20]
        return "text:" + digest, "1"


def seen_path(session_dir: Path, session_id: str) -> Path:
    return Path(session_dir) / session_id / SEEN_FILE


def read_seen(path: Path) -> dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    seen = data.get("seen") if isinstance(data, dict) else None
    return {str(k): str(v) for k, v in seen.items()} if isinstance(seen, dict) else {}


def _write_seen(path: Path, seen: Mapping[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps({"seen": dict(seen)}, ensure_ascii=False, indent=0) + "\n",
                   encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def budget_chars(config: Any, kind: str, budget_tokens: int | None = None) -> int | None:
    """The character budget of one hook: ``prompt`` and ``stop`` are bounded, the session
    brief is bounded by its own line cap."""
    if budget_tokens is not None:
        return int(budget_tokens) * CHARS_PER_TOKEN
    hooks = getattr(config, "hooks", None)
    if kind == "prompt":
        return int(getattr(hooks, "prompt_tokens", 200)) * CHARS_PER_TOKEN
    if kind == "stop":
        return int(getattr(hooks, "stop_tokens", 150)) * CHARS_PER_TOKEN
    return None


class Emitter:
    """The emitter of one hook call: ``add`` as many times as needed, then ``close``."""

    def __init__(self, path: Path, kind: str, budget: int | None,
                 cap_lines: int | None = None) -> None:
        self.path = path
        self.kind = kind
        self.budget = budget
        self.cap_lines = cap_lines
        self.seen = read_seen(path)
        self.used = 0
        self.count = 0
        self.emitted: dict[str, str] = {}
        self.headers_done: set[str] = set()

    def is_new(self, subject: str, state: str = "1") -> bool:
        key = (subject, state or "-")
        return self.seen.get(key[0]) != key[1] and self.emitted.get(key[0]) != key[1]

    def fresh(self, lines: Iterable[Line]) -> list[Line]:
        """The lines that are new to this session (nothing is marked)."""
        return [line for line in lines if line.text and self.is_new(*line.key())]

    def add(self, lines: Sequence[Line], *, headers: Mapping[str, str] | None = None,
            commit: bool = True) -> list[str]:
        """The lines to print: the new ones, within the budget, headers before their group,
        and one ``+N more: plumb show ...`` line for the records the budget cut. With
        ``commit`` False nothing is counted or marked (a preview, for kept lines)."""
        headers = headers or {}
        used, count = self.used, self.count
        done = set(self.headers_done)
        out: list[str] = []
        cut: list[str] = []
        taken: list[Line] = []
        progressed = False
        keys: set[tuple[str, str]] = set()
        for line in self.fresh(lines):
            if line.key() in keys:
                continue
            keys.add(line.key())
            header = headers.get(line.group or "") if line.group not in done else None
            cost = len(line.text) + (len(header) if header else 0)
            over = self.budget is not None and used + cost > self.budget
            capped = self.cap_lines is not None and count >= self.cap_lines
            if not line.kept and (capped or (over and progressed)):
                if line.record:
                    cut.append(line.record)
                continue
            if header:
                out.append(header)
                done.add(line.group or "")
            out.append(line.text)
            used += cost
            count += 1
            progressed = progressed or not line.kept
            taken.append(line)
        if cut:
            more = f"plumb: +{len(cut)} more relevant: plumb show " + " ".join(cut)
            out.append(more if len(more) <= MORE_WIDTH else more[: MORE_WIDTH - 3] + "...")
        if commit:
            self.used, self.count, self.headers_done = used, count, done
            for line in taken:
                subject, state = line.key()
                self.emitted[subject] = state
                for mark in line.marks:
                    self.emitted[mark] = "1"
        return out

    def close(self) -> None:
        """Mark what was emitted as seen (one write; nothing when nothing was emitted)."""
        if not self.emitted:
            return
        merged = {**self.seen, **self.emitted}
        try:
            _write_seen(self.path, merged)
        except OSError:
            pass
        self.seen = merged
        self.emitted = {}


def open_emitter(ctx: Any, kind: str, *, budget_tokens: int | None = None,
                 cap_lines: int | None = None, config: Any = None) -> Emitter:
    """The emitter of hook ``ctx`` (a ``HookContext``): ``kind`` is ``session-start``,
    ``prompt`` or ``stop``."""
    if config is None and budget_tokens is None:
        try:
            from plumb.config import load_config

            config = load_config(ctx.root)
        except Exception:  # noqa: BLE001 - a broken config keeps the defaults
            config = None
    return Emitter(seen_path(ctx.session_dir, ctx.session_id), kind,
                   budget_chars(config, kind, budget_tokens), cap_lines)


def emit(ctx: Any, lines: Sequence[Line | str], kind: str, *,
         budget_tokens: int | None = None, headers: Mapping[str, str] | None = None,
         config: Any = None) -> list[str]:
    """One-shot: the new lines of ``lines`` within the budget, marked seen."""
    emitter = open_emitter(ctx, kind, budget_tokens=budget_tokens, config=config)
    out = emitter.add([line if isinstance(line, Line) else Line(line) for line in lines],
                      headers=headers)
    emitter.close()
    return out


def reset(session_dir: Path, session_id: str) -> None:
    """Forget what the agent has seen (``/clear``, compaction)."""
    try:
        seen_path(session_dir, session_id).unlink()
    except OSError:
        pass
