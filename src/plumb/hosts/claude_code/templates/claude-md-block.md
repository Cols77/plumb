<!-- plumb:begin -->
## plumb

- Records of the owner's intent live in `.plumb/` (INT, SR, DEC, FEAT, NC); the test map is
  `.plumb/test_map.txt`.
- Read back each request and record it as proposed: say in the owner's terms what will and
  won't be done, with assumptions labelled, then record an SR with given/when/then examples
  (edge cases too) and link it `implemented_by` the code it changes. It never blocks the work.
  Wait for plumb's check (`{plumb} clarify --wait`) only after the owner types
  `/plumb clarify <words>`; otherwise `clarify --wait --json` only gives the message digest.
- `{plumb} brief` prints the current intent; `{plumb} status` shows what awaits the owner;
  `{plumb} show <ID>` prints a record's examples and tests; `{plumb} explain <words>` says why
  something exists.
<!-- plumb:end -->
