"""Durable source-session action journal and next-turn handoff. Never owner prompts."""

from pathlib import Path

from plumb.mod.session import now
from plumb.understand import files


def directory(root: Path, session: str) -> Path:
    return files.session_dir(root, session) / "browser-actions"


def path(root, session, request_id):
    return directory(root, session) / (files.digest_of(request_id)[7:] + ".json")


def read(root, session, request_id):
    return files.read_json(path(root, session, request_id))


def write(root, session, data):
    files.write_json_atomic(path(root, session, data["id"]), data)


def entries(root, session):
    found = [files.read_json(p) for p in directory(root, session).glob("*.json")]
    return sorted(
        (data for data in found if isinstance(data, dict)),
        key=lambda data: (data.get("sequence", 0), data.get("created", ""), data["id"]),
    )


def history(root, session):
    out = []
    for data in entries(root, session):
        if isinstance(data, dict):
            # Do not expose the server key (never persisted) or internal request bookkeeping.
            out.append(
                {k: data[k] for k in ("id", "card", "status", "created", "delivered") if k in data}
            )
    return out


def recover(root, session):
    """An interrupted action is never replayed; hand its uncertainty to the same agent.

    The journal was written before any effect, so even a crash between answer and receipt
    cannot lose the correction. The agent must inspect durable Plumb evidence to reconcile.
    """
    for data in entries(root, session):
        if isinstance(data, dict) and data.get("status") == "pending":
            write(
                root,
                session,
                {
                    **data,
                    "status": "queued",
                    "model_note": "Browser answer recording was interrupted for card "
                    + str(data.get("card"))
                    + ". Do not assume it was applied or repaired. Inspect the card and logged "
                    "press/approval evidence before continuing; do not repeat the action blindly.",
                },
            )


def pending(root, session):
    from plumb.present.delta import Line

    out = []
    for data in entries(root, session):
        if isinstance(data, dict) and data.get("status") == "queued":
            note = str(data.get("model_note") or "")
            correction = data.get("text")
            if correction:
                note += "\nOwner correction supplied in the browser: " + correction
            text = "plumb browser answer (source session " + session + "): " + note
            out.append((data, Line(text, oneshot=True)))
    return out


def preserve(ctx):
    """Keep handoff context before any budget-sensitive work, then acknowledge it.

    'Delivered' means preserved to this matching hook's output, not agent execution.
    All subsequent prompt keeps include these same oneshot lines.
    """
    entries = pending(ctx.root, ctx.session_id)
    lines = [line for _, line in entries]
    ctx.kept.retained.extend(line.text for line in lines)
    ctx.keep([*ctx.kept.snapshot(), *(line.text for line in lines)])
    for data, _ in entries:
        write(ctx.root, ctx.session_id, {**data, "status": "delivered", "delivered": now()})
    return lines
