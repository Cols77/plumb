<!-- iaso:begin -->
## iaso

- Records of the owner's intent live in `.iaso/` (INT, SR, DEC, FEAT, NC); the test map is
  `.iaso/test_map.txt`.
- Formalize each request that changes the system into proposed records linked to the code it
  changes, for the judge to validate: an SR with given/when/then examples (edge cases too),
  linked `implemented_by` the code it changes. Ask the owner to read nothing back; it never
  blocks the work.
  Then run `{iaso} clarify --wait --json` and ask iaso's judge's questions it returns with
  the question tool, all at once as soon as raised, each in the owner's terms (`{iaso}
  question reword`, merging those on one principle); never drop, answer or default one.
  It checks the request itself only after `/iaso clarify <words>`.
- `{iaso} brief` prints the current intent; `{iaso} status` shows what awaits the owner;
  `{iaso} show <ID>` prints a record's examples and tests; `{iaso} explain <words>` says why
  something exists.
<!-- iaso:end -->
