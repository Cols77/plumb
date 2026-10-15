# Plumb workspace third-party notices

The browser distribution includes the complete licenses in
`assets/THIRD_PARTY_NOTICES.txt`, generated before every build.

- **Escouade**, revision `34322c696757790dd32589311f46c662c057ebd0`,
  Copyright (c) 2026 Guillaume Gagnaire, MIT. Extracted warm charcoal theme tokens,
  local font pairing, `Splitter.svelte`, `DiffView.svelte`, `lib/diff.ts` and
  `lib/resize.ts`. Adaptations remove Tauri, tooltip and translation dependencies;
  the splitter supports a pane on its right. Plumb supplies actual stored field
  differences. No Escouade agent runtime or application state is included.
- **diagram-mod**, revision `050643c9e1ce2ae942a0ffa2c2d8cf9404e15bdc`,
  Copyright (c) 2026 Colin AUBE, MIT. `hooks/svg.ts` and `hooks/model.ts` are
  copied without changes into `src/lib/diagram-mod/`. No Claude adapter is included.
  Preparation is followed by DOMPurify sanitization, external-resource removal and
  bounded description parsing; diagrams render as SVG image Blobs.
- **Hanken Grotesk** and **JetBrains Mono**, locally bundled through pinned
  `@fontsource` packages, SIL Open Font License 1.1. Original full OFL notices are
  included in the generated notices. The fonts are not modified or renamed.
- **Svelte**, **clsx**, and **esm-env**, MIT; **DOMPurify**, Apache-2.0 OR MPL-2.0.
  Exact installed versions and original license texts are included in the generated
  notices. `package-lock.json` pins the complete dependency graph.

The original extracted-source MIT notices are retained in `ui/licenses/`.
`scripts/notices.mjs` reads those files and the installed runtime/font licenses;
it does not require upstream checkouts or network access.
