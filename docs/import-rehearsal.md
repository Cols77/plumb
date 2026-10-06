# Import rehearsal: pi-agent-factory into an exported copy

Fork plan F3 and next-plan 9.5, run by the IMPORT lane on 2026-10-06 with the completed
importer (`plumb import pi-agent-factory`, SR-058 to SR-060). Everything ran in a scratch
directory. pi-agent-factory was only read: its files were opened read-only, and the only
git commands were `rev-parse`, `status` and `archive`.

## Recipe

```bash
SCRATCH=<a scratch directory>
# 1. dry run into an empty target: the plan as a diff, nothing written
mkdir -p "$SCRATCH/probe" && git -C "$SCRATCH/probe" init -q
uv run plumb init --root "$SCRATCH/probe"
uv run plumb import pi-agent-factory C:/coding/pi-agent-factory --dry-run --root "$SCRATCH/probe"
# 2. two exported copies of the source's HEAD, each imported; the first one twice
for n in 1 2; do
  mkdir -p "$SCRATCH/paf$n" && git -C C:/coding/pi-agent-factory archive HEAD | tar -x -C "$SCRATCH/paf$n"
  git -C "$SCRATCH/paf$n" init -q && uv run plumb init --root "$SCRATCH/paf$n"
done
uv run plumb import pi-agent-factory C:/coding/pi-agent-factory --root "$SCRATCH/paf1"
uv run plumb import pi-agent-factory C:/coding/pi-agent-factory --root "$SCRATCH/paf1"   # no change
uv run plumb import pi-agent-factory C:/coding/pi-agent-factory --root "$SCRATCH/paf2"
uv run plumb validate --root "$SCRATCH/paf1"
```

## Results (source HEAD 341e2a08, the checkout's working tree)

| Check (next-plan 9.5) | Result |
|---|---|
| 1. Dry run prints the diff, leaves the source unchanged | 131 `create` lines, 9 `approve ... by import` lines, the claims lines; the probe's `.plumb/` byte-identical before and after; the source's `git status --porcelain` and the SHA-256 of its 383 register, consent, spec, bundle and ingest files identical before and after all runs |
| 2. Two consecutive imports give identical trees | The second import of `paf1`: 0 created, 0 updated, 131 unchanged, no file changed, no event appended. `paf1` and `paf2` hold byte-identical record files and `claims.yaml` (132 files) |
| 3. Every `by: import` approval cites a consent pinning current content | 9 approvals (SR-077 to SR-084, SR-091), one entry right after the `import` event, each record citing its consent path, consent digest, consented requirement digest, run and upstream hash. 6 SRs (SR-085 to SR-090) have a consent pinning older content: `consent-stale`, proposed. Tests cover current, older (LF and CRLF forms), non-human, wrong-phrase, reasonless and malformed consent |
| 4. Symbol and test-node ends hashed and checked | 638 links, all current: 401 file, 148 symbol (every structured `symbol` binding resolved in its file), 86 record, 3 test-node ends. `plumb validate`: 0 errors |
| 5. Findings counted by kind; never into plumb's own repository | 54 findings: 35 `missing-end`, 7 `checksum-ok`, 6 `consent-stale`, 6 `membership-difference`. The importer refuses a target whose `pyproject.toml` names the project `plumb` (exit 2) |

Records: 85 SR, 24 FEAT, 22 NC, all proposed except the 9 confirmed by import. `claims.yaml`:
8 exempt globs added to plumb's defaults, the epoch kept, 371 baseline entries
`{commit, path, nc}` mapped from the 432 NC-0011 `{sr, path}` pairs through the 305
ingested commits (no pair unmapped). One `claims-ingest` event holds the checkpoint
(`d8b52aa5`) and those commits.

`plumb validate` on the copy: 0 errors, 94 warnings: 85 `no-intent` (pi-agent-factory has no
INT records), 8 `uncovered` (requirements confirmed by import whose acceptance criteria name
tests not written yet), 1 summary of the 122 proposed records.

## Timing (2 cores)

| Step | Before (fork plan 5.2) | Now |
|---|---|---|
| Dry run into an empty target | about 1 s | 1.2 s |
| Import into the exported copy | 2 min 14 s | 17.2 s (each record file written once, links pinned in the same pass) |
| The same import again (no change) | n/a | 5.6 s |
| `plumb validate` on the copy | 1.2 s | 3.2 s (symbol ends parse their files) |

`plumb drift` takes 10 to 23 s on the copy and `plumb status` 11.7 s, most of it
in the test map's `verified_tests` (VERIFY code, quadratic in links at this scale); see
`docs/followups.md`.

## Findings that need the owner (fork plan F3 step 2)

- **Membership differences (6)**, meaning-changing, unchanged since the first rehearsal:
  FEAT-001 (SR-050, SR-057, SR-058, SR-064 only in the document), FEAT-002 (SR-059,
  SR-063), FEAT-010 (SR-056); no bundle for FEAT-018, FEAT-019, FEAT-020. The union is
  imported; each needs the owner's decision.
- **Stale consents (6)**: SR-085 to SR-090 changed after their consent; they arrive
  proposed and need the owner's confirmation.
- **Missing ends (35)**: `verified_by` tests that requirements name before they exist
  (SR-077 to SR-090). Real gaps, not import errors.
- The 8 `spec:` relations of the first rehearsal now resolve: each becomes a `relates_to`
  link to the spec document declaring that id (`docs/coherence/specs/*.md`).
