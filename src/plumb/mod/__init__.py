"""The Python side of the Claude Code mod (sp7-owner-surface 5.1, 5.7; sp7-realign-sp8 C4, C6).

- ``session``: ``plumb mod hello`` registers the mod's key digest for a session in
  ``.plumb/session/<id>/mod.json`` (the first registration wins) and checks a press's key;
- ``offers``: the cards the room draws, each question with its offer and buttons, recorded when
  drawn (``offers/<offer>.json`` and an ``offer`` log entry);
- ``press``: the room's button answers a drawn card through ``understand.answer``'s one
  answer path with the ``Button`` source; every press is logged as a ``card-press``;
- ``cli``: the routed command.

The key never leaves the mod: it reaches plumb on stdin only, and only its digest is written.
Every command refuses (exit 3, nothing written) under the agent session marker."""
