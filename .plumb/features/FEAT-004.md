---
id: FEAT-004
title: Other hosts, adapters kept for later
description: One host-neutral core with thin adapters for Codex and Hermes, kept for later and not frozen
  (owner, 2026-11-03); the Pi adapter, the read-only MCP server and the pi-agent-factory import are removed
  (SR-380).
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
    from: sha256:ef04a58e89a029a4ea703f3292b05f9aae079d565e8fada914cd6c4f25718bf5
    to: sha256:ee1233dd11bc2d0cd7106bc544fcea00a0664028458ce57e953e8683546c7950
- kind: derives_from
  to: INT-085
  pin:
    from: sha256:ef04a58e89a029a4ea703f3292b05f9aae079d565e8fada914cd6c4f25718bf5
    to: sha256:7164d79ea15e2220ad12e2426e570954e9ebca7d3eff5f3d9fd85ee025325bdf
---
