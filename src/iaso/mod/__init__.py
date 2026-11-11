"""The Python side of the Claude Code mod (sp7-owner-surface 5.1, 5.7; SR-380: no card is drawn or pressed).

- ``session``: ``iaso mod hello`` registers the mod's key digest for a session in
  ``.iaso/session/<id>/mod.json`` (the first registration wins) and checks a press's key;
- ``cli``: the routed command.

The key never leaves the mod: it reaches iaso on stdin only, and only its digest is written.
Every command refuses (exit 3, nothing written) under the agent session marker."""
