<!-- plumb:begin -->
## plumb

- Records of the owner's intent live in `.plumb/` (INT, SR, DEC, FEAT, NC); the test map is
  `.plumb/test_map.txt`.
- Formalize each request that changes the system into proposed records linked to the code it
  changes, for the judge to validate: an SR with given/when/then examples (edge cases too),
  linked `implemented_by` the code it changes. Ask the owner to read nothing back; it never
  blocks the work.
  Then run `{plumb} clarify --wait --json` and ask plumb's judge's questions it returns with
  the question tool, all at once as soon as raised, each in the owner's terms (`{plumb}
  question reword`, merging those on one principle); push an obvious or answered one back
  (`{plumb} question pushback`); never drop, answer or default one. It checks the request
  itself only after `/plumb clarify <words>`.
- `{plumb} brief` prints the current intent; `{plumb} status` shows what awaits the owner;
  `{plumb} show <ID>` prints a record's examples and tests; `{plumb} explain <words>` says why
  something exists.
<!-- plumb:end -->
