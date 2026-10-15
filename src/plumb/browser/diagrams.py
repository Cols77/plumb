"""Read only a current card's bounded, project-local diagram as inert text."""

from pathlib import Path

LIMIT = 131072


def read(root: Path, source: str):
    result = {"source": source, "text": None, "error": None}
    if not source:
        return {**result, "error": "This card has no diagram"}
    try:
        base = root.resolve()
        target = (base / source).resolve()
        if not target.is_relative_to(base):
            return {**result, "error": "Diagram path resolves outside the project"}
        if not target.is_file():
            return {**result, "error": "Diagram file is missing"}
        # Bound bytes before decoding; Unicode still has a separate character bound.
        with target.open("rb") as stream:
            raw = stream.read(LIMIT * 4 + 1)
        if len(raw) > LIMIT * 4:
            return {**result, "error": "Diagram is too large (131072 character limit)"}
        text = raw.decode("utf-8")
        if len(text) > LIMIT:
            return {**result, "error": "Diagram is too large (131072 character limit)"}
        return {**result, "text": text}
    except (OSError, ValueError, UnicodeError):
        return {**result, "error": "Diagram could not be read as UTF-8 text"}
