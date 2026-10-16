<!-- plumb:begin -->
## plumb

- Records of the owner's intent live in `.plumb/` (INT, SR, DEC, FEAT, NC); the test map is
  `.plumb/test_map.txt`.
- Read back each request and record it as proposed: say in the owner's terms what will and
  won't be done, with assumptions labelled, then record an SR with given/when/then examples
  (edge cases too) and link it `implemented_by` the code it changes. It never blocks the work.
  Then run `{plumb} clarify --wait --json` and ask plumb's judge's questions it returns with
  the question tool, verbatim; it checks the request itself only after `/plumb clarify <words>`.
- `{plumb} brief` prints the current intent; `{plumb} status` shows what awaits the owner;
  `{plumb} show <ID>` prints a record's examples and tests; `{plumb} explain <words>` says why
  something exists.
<!-- plumb:end -->
