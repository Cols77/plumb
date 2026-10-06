"""Every SP6 owner-visible string, the R14 choke point (SP6 spec 11.1).

Owner text names a ``/plumb`` command or the plain words to say, never a shell command.
``bare_cli_verbs`` finds a bare ``plumb <verb>`` in a text, so each surface's test can assert
that it names none.

This module belongs to the coordinator (plan 3.2 item 9); the LOGS lane wrote the part it
needs (``LEGACY_LOG`` and ``bare_cli_verbs``) because phase 0 had not run when the lane
started. The other lanes' constants join it at Integrate.
"""

from __future__ import annotations

import re

# 6.5, 10: the warning in plumb validate and in the merge report while legacy lines remain
LEGACY_LOG = ("plumb: {n} log entries are still in the old format (say \"migrate the logs\", "
              "or /plumb migrate the logs)")

_BARE = re.compile(r"(?<![\w/.-])plumb[ \t]+([a-z][a-z-]*)")


def bare_cli_verbs(text: str) -> list[str]:
    """Every ``plumb <verb>`` in ``text`` whose verb is a CLI route, not preceded by ``/``
    and not directly followed by ``:`` (so ``/plumb merge-fix`` and the label
    ``plumb log: ...`` pass, ``plumb merge-fix`` and ``uv run plumb log migrate`` do not)."""
    from plumb.cli import ROUTES

    out: list[str] = []
    for match in _BARE.finditer(text):
        verb = match.group(1).rstrip("-")
        if text[match.end():match.end() + 1] == ":":
            continue
        if verb in ROUTES:
            out.append(f"plumb {verb}")
    return out
