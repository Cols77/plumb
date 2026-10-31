---
id: FEAT-004
title: Other hosts, frozen while Claude Code is the agent
description: One host-neutral core with thin adapters for Codex and Hermes, frozen while Claude Code is
  the agent working on plumb; the Pi adapter, the read-only MCP server and the pi-agent-factory import
  are removed (SR-380).
requirements:
- SR-238
- SR-282
- SR-283
- SR-284
- SR-285
links:
- kind: derives_from
  to: INT-088
  pin:
    from: sha256:555b0767a4053a2584e724d2d5518637f4be53c417e7c21e621c036f3c172418
    to: sha256:c060d99359c390a33f26428660c7dad3e445f35288f22c0b13b1bf6cd4a6c20b
- kind: derives_from
  to: INT-085
  pin:
    from: sha256:555b0767a4053a2584e724d2d5518637f4be53c417e7c21e621c036f3c172418
    to: sha256:7164d79ea15e2220ad12e2426e570954e9ebca7d3eff5f3d9fd85ee025325bdf
---
