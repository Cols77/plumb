---
id: FEAT-004
title: Other hosts, the read-only MCP server and the pi-agent-factory import
description: One host-neutral core with thin adapters for Codex, Pi and Hermes, a read-only MCP server,
  and the read-only import of pi-agent-factory.
requirements:
- SR-238
- SR-282
- SR-283
- SR-284
- SR-285
links:
- kind: derives_from
  to: INT-007
  pin:
    from: sha256:6e365659e968a061c4fee3200c555aa26b97d9d28adfb973697888732737067a
    to: sha256:c4cd9ab0fb7aa5d3f12ea8cf57b723d2c4027a70bee48baeae63f49bcc5a4df1
- kind: derives_from
  to: INT-005
  pin:
    from: sha256:6e365659e968a061c4fee3200c555aa26b97d9d28adfb973697888732737067a
    to: sha256:c50d23dc19e322bff0fe66ac394061a53ffe533d5597e6e2c13c3c7514462a63
- kind: derives_from
  to: INT-010
  pin:
    from: sha256:6e365659e968a061c4fee3200c555aa26b97d9d28adfb973697888732737067a
    to: sha256:7975be2cbf3b64fda12a0a618395daeba91020d7af1fb7d35d9ded2173a87a20
---
