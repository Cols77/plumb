<!-- plumb:begin -->
## plumb

- Records of the owner's intent live in `.plumb/` (INT, SR, DEC, FEAT, NC); the test map is
  `.plumb/test_map.txt`.
- Read back each request and record it as proposed: say in the owner's terms what will and
  won't be done, with assumptions labelled, then record an SR with given/when/then examples
  (edge cases too) and link it `implemented_by` the code it changes. It never blocks the work.
- `.venv/Scripts/python.exe -m plumb brief` prints the current intent; `.venv/Scripts/python.exe -m plumb status` shows what awaits the owner.
<!-- plumb:end -->
