# Local browser API

Launch `plumb ui --root PATH --port 8765 --open --assets PATH`. `--assets` names a
built directory containing `index.html` and `assets/`. Without assets the API remains
available and the CLI reports the missing build. `--demo` uses a fresh temporary
project and never loads the owner's repository; demo records are explicitly labelled.

The server binds only `127.0.0.1`. The launch link carries `#token=CAPABILITY`; the
client removes the fragment and sends `Authorization: Bearer CAPABILITY` on API
requests. Never put the capability in query strings. The server emits no request logs.
It requires the exact bound Host, rejects any foreign Origin, and requires its exact
Origin on POST. JSON bodies are objects, at most 65536 bytes. Static routes are `/`
and `/assets/...`, from the explicit build directory only. Repository HTML is never
served as a document.

| Method and route | Body | Result |
| --- | --- | --- |
| GET `/api/workspace` | — | `{project:{name,root,demo},sessions:[{id,counts:{waiting,processing,blocked,done,left_open}}]}` |
| POST `/api/sessions/{id}/draw` | `{}` | `{session,cards:[Card],followups:[Followup]}` |
| POST `/api/sessions/{id}/press` | `{offer,choice,request_id,text?}` | Existing mod press result plus `{duplicate,followup:{id,status}}` |
| GET `/api/sessions/{id}/diagram?card=ID` | — | `{source,text,error}`; text null on unavailable/unsafe/oversized source |
| GET `/api/studies` | — | `{studies:[Study without body],understanding:Understanding}` |
| POST `/api/studies/{slug}/open` | `{}` | `Study` with `body`; a `new` study becomes `opened` |
| POST `/api/studies/{slug}/mark` | `{mark:"known"\|"deeper"}` | `{study:Study,understanding:Understanding}` |
| POST `/api/understanding` | `{text}` | `Understanding` after saving the owner's text (at most 65536 characters) |

Session IDs must exactly match existing source-session directories; they are not
normalized from arbitrary input. Requests are serialized within the browser server,
and every operation opens a fresh Core. Cards are not copied to a browser session.

`Card` retains the mod draw fields: `id`, `kind`, `topic`, `issue`, `evidence`,
`resolutions`, `questions`, `status`, `answers`, `turn`, `branch`, `repeats`, `state`,
`reason`, `offers`, and `content`. Settled cards join the same list, with no offers.
`content` is the existing full-card schema from `offers.content_for`, including context,
options and consequences. `status` is stored state; `state` is computed. In particular,
an answer or `done` card is not a claim that implementation was repaired.

Browser additions:

- `records`: `{id,title,hash,body,fields,status}` for related current records. Status is
  the full RecordStatus JSON, including confirmation and link states. No verification
  evidence is invented.
- `diff`: null, or actual stored merge conflict `{record,labels:{ours,theirs},fields,
  proposed}`. Each field contains the available `base`, `ours`, and `theirs` values.
- `diagram`: `{source,available,error}`. The endpoint reads only this current card's
  source, resolves it under the project, and limits it to 131072 Unicode characters
  and 524288 bytes. The client must extract/sanitize SVG; never execute returned HTML.

Studies and the understanding picture (SR-292..294; DEC-151, DEC-152, DEC-154) are a
section beside the questions, project-wide rather than per session. `Study` is
`{slug,title,topic,step,loop,why,status,body?}` from `.plumb/studies/<slug>.md`; `status`
is `new`, `opened`, `known` or `deeper`, and `body` is plain words with an optional
```` ```mermaid ```` block, shown as text. `Understanding` is `{text,knows,needs}` from
`.plumb/understanding.md` (`- knows: ...` and `- needs: ...` lines). Reading a study opens
it, which clears the band's study line. 'I know this' (`known`) writes a `knows` line for
its topic and 'Go deeper' (`deeper`) a `needs: <topic> (deeper)` line; neither is an answer:
nothing is queued, logged as a press or delivered to a session. A study about an open
conflict lays out both sides and has no resolution button. Plumb never opens the room by
itself when a study is written. Slugs are 1–80 letters, digits or hyphens.

Offers carry their own `offer_id`, question, record, exact shown hash, buttons and draw
timestamp. Always submit the button's stored `index`; content-option positions are not
button indices. Browser offer IDs additionally bind displayed card meaning and full
content. If options/context change, the old offer refuses. Registrations and offer
files are separate (`browser.json`, `browser-offers/`) and leave `mod.json` untouched.
The server's signing key remains only in memory. Approval/rejection provenance uses
explicit browser surface and marker-free registration/offer logs; mod verification
remains separate. Those logs support recheck after runtime session files disappear.

`request_id` is 1–128 ASCII letters, digits, hyphens or underscores. Repeating a
completed request returns its stored result without applying it again. Reusing an ID
for different content refuses. An identical completed offer/choice/text also deduplicates
across IDs only while it remains the latest action for that card. A distinct
answer to an already answered question refuses.

`Followup` is `{id,card,status,created,delivered?}`. A successful answer queues its
existing `model_note` and optional owner correction for the **source session's next
prompt hook**. `delivered` means retained in matching-session hook output with `ctx.keep`
and a one-shot line; it does not mean that an agent was awakened or acted. The note is
never logged as an owner prompt and is never passed through OwnerWords. A durable
intent precedes answer effects. An interrupted process recovers an explicitly uncertain
handoff on restart and refuses blind action replay; the agent must inspect the durable
press/approval/card evidence. A completed receipt and handoff history survive restart.

Errors are JSON `{error:string}` with 400 malformed input, 401 missing capability,
403 Host/Origin refusal, 404 unknown route/session/card, 409 refused owner action,
413 oversized body, 415 wrong content type, or 500 internal operation failure.

Concurrency limit: the browser lock protects concurrent tabs served by that process.
Existing independent mod/worker processes still use the repository's original card-store
write semantics; this change does not add repository-wide transactions. Presentation
and record hashes are rechecked immediately before applying an answer. A second server
registering the same session rotates its browser key; the older server's actions fail
explicitly rather than silently changing credentials.
