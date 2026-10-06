"""Every SP6 owner-visible string, in one place (sp6 11.1, R14).

No text SP6 shows the owner names a bare ``plumb <verb>`` or any other shell command: it
names a ``/plumb`` command or the plain words to say. Lanes import these constants and
format functions and never inline owner wording; ``bare_cli_verbs`` is the test every
surface's output passes.

The coordinator owns this module (plan 3.2 item 9). Phase 0 had not run when the AWARENESS
lane started, so this lane wrote the part it needs (sp6 9.4 and ruling R17); the other lanes'
constants join it at Integrate.
"""

from __future__ import annotations

import re

# -- AWARENESS (sp6 9.4, SR-078): one line per record another worktree or branch changes
OVERLAP = 'plumb: {id} "{title}" is also being changed on branch {branch}'
OVERLAP_WORKTREE = " (worktree {worktree})"
OVERLAP_CLAIMED = ' (intent in flight there: "{summary}")'
MORE_OVERLAPS = "plumb: +{n} more also being changed elsewhere (/plumb status)"
OVERLAP_CARD = "{n} also changed on {labels}"
OVERLAP_CARD_ASCII = "overlap {n} ({labels})"
CONFLICTS_CARD = "{n} conflict awaits you"
CONFLICTS_CARD_PLURAL = "{n} conflicts await you"
STATUS_OVERLAPS_HEADER = "also being changed elsewhere (ask \"is anyone else changing X?\"):"
STATUS_NO_OVERLAPS = "also being changed elsewhere: nothing"

# -- intent in flight (ruling R17, SR-080, SR-081): the early intent-conflict card
EARLY_CARD_HEAD = '▸ Conflict  {id} "{title}"   (awaits your choice, before any work)'
EARLY_CARD_SIDE = "  {label:<10}  {text}"
EARLY_CARD_JUDGED = "  Compatible? {judgment}"
EARLY_CARD_SAME = "the same requirement is being changed on both branches"
EARLY_CARD_SAY = ('  Say: "keep {branch}\'s", "keep this one", or "both" (and how they '
                  "combine)")
EARLY_QUESTION = 'Branch {branch} says "{theirs}"; this request says "{ours}": which one, or both?'
EARLY_CHOSEN = "this request's version"
EARLY_THEIRS = "{branch}'s version"
EARLY_BOTH = "both, combined"
EARLY_RECORDED = ("plumb: asked once for every branch working on {id} \"{title}\"; the answer "
                  "settles it there too")
EARLY_ASK = ("plumb: {dec} holds that question for the agent: show the card above and ask the "
             "owner now, before any implementation, then build on the answer")
EARLY_KNOWN = ('plumb: {id} "{title}": the owner is asked on branch {branch} whether this work '
               "or that branch's holds; build on the answer")
EARLY_SETTLED = ('plumb: {id} "{title}": the owner settled it on branch {branch}: "{chosen}"; '
                 "build on that")
EARLY_COMPATIBLE = ('plumb: {id} "{title}" shares its feature with intent in flight on branch '
                    '{branch} ("{summary}"); judged compatible, nothing to ask')
EARLY_DRY_RUN = "plumb: nothing recorded (a preview)"
INFLIGHT_BUSY = ("plumb: could not record this work's intent for the other branches (another "
                 "session is recording at the same moment); it is retried at the end of the "
                 "turn")
INFLIGHT_NONE = "intent in flight on other branches: none"
INFLIGHT_HEADER = "intent in flight on other branches:"
INFLIGHT_LINE = '  {branch}: "{summary}" ({records})'


_PLUMB_VERB = re.compile(r"(?<![/\w.-])plumb[ \t]+([a-z][a-z-]*)")
# the SP6 verbs, recognised even before their routes exist in this build
_SP6_VERBS = frozenset({"merge-fix", "ids", "log", "merge-driver", "conflict", "conflicts",
                        "inflight"})


def bare_cli_verbs(text: str) -> list[str]:
    """Every ``plumb <verb>`` in ``text`` whose verb is a CLI route, not preceded by ``/``
    and not directly followed by ``:`` (so ``/plumb merge-fix`` and the label "plumb log:
    not available" pass, while ``plumb merge-fix`` and ``uv run plumb log migrate`` do
    not)."""
    from plumb.cli import ROUTES

    out: list[str] = []
    for match in _PLUMB_VERB.finditer(text):
        verb = match.group(1).rstrip("-")
        if text[match.end():match.end() + 1] == ":":
            continue
        if verb in ROUTES or verb in _SP6_VERBS:
            out.append(f"plumb {verb}")
    return out
