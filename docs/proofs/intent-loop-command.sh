#!/bin/sh
# Command proof of SR-194 and SR-197 in a scratch repository (no hook, no model).
SRC=/c/coding/plumb-wt/intent-loop/src
PY=C:/coding/plumb/.venv/Scripts/python.exe
R=$(mktemp -d)
cd "$R" || exit 9
git init -q . && git config user.email p@x && git config user.name proof
run() { echo "\$ plumb $*"; PYTHONPATH=$SRC $PY -m plumb "$@" 2>&1; echo "[exit $?]"; echo; }
run init
run new intent --title "multiply next to add" --quote "add multiply next to add" --readback "a multiply command beside add"
run new requirement --title "multiply two numbers" --statement "multiply(a, b) returns a times b" --derives-from INT-001
echo "# the loop state the commanded /plumb intent message opens (seeded with cmd_intent.open_loop; the prompt hook is not run here)"
PYTHONPATH=$SRC $PY -c "from plumb.understand import cmd_intent; print(cmd_intent.open_loop('.', 's1', 'sha256:' + 'b'*64).as_posix())"
echo '[{"level":"low","what":"wording"}]' > low.json
echo '[{"level":"high","what":"multiply of floats is not said"}]' > high.json
echo "## SR-194: stages out of order refuse, naming the gate"
run intent gate plan --intent INT-001 --findings low.json --session s1
run intent done --intent INT-001 --session s1
run intent status --session s1
echo "## SR-194: a high finding keeps the clarify gate shut"
run intent gate clarify --intent INT-001 --findings high.json --session s1
echo "## SR-194: in order, each gate is recorded"
run intent gate clarify --intent INT-001 --findings low.json --session s1
run intent gate plan --intent INT-001 --findings low.json --session s1
run intent status --session s1
echo "events logged:"; for f in .plumb/log/intent-*/*.json; do echo "$f"; cat "$f"; echo; done
echo
echo "## SR-197: the proof is stated, the build is finished, the proof not shown"
run proof SR-001 --plan "run multiply 2 3 and see 6" --kind command
run intent done --intent INT-001 --session s1
echo "## SR-197: the proof shown and its evidence recorded"
echo "multiply 2 3 -> 6" > out.txt
run proof SR-001 --evidence out.txt --summary "multiply printed 6" --passed
run intent done --intent INT-001 --session s1
run intent status --session s1
echo "intent-done events:"; cat .plumb/log/intent-done/*.json; echo
cd / && rm -rf "$R"
