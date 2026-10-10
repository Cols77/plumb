#!/bin/sh
# plumb: the check before an edit tool runs (SR-103). Shell only: no interpreter, no other program,
# so it answers fast. It reads the hook's JSON on stdin and the one small gate file of the
# session; while that file says closed it refuses Edit, Write, MultiEdit and NotebookEdit.
# Edits made through the shell (redirects, in-place editors) are not checked by this guard.
input=
while IFS= read -r line || [ -n "$line" ]; do input="$input$line"; done
tool=${input#*\"tool_name\"}
tool=${tool#*\"}
tool=${tool%%\"*}
case "$tool" in
  Edit|Write|MultiEdit|NotebookEdit) ;;
  *) exit 0 ;;
esac
session=${input#*\"session_id\"}
session=${session#*\"}
session=${session%%\"*}
case "$session" in
  ""|*[!A-Za-z0-9_-]*) exit 0 ;;
esac
file="${CLAUDE_PROJECT_DIR:-.}/.plumb/session/$session/gate"
[ -r "$file" ] || exit 0
state=
while IFS= read -r line || [ -n "$line" ]; do state="$state$line"; done < "$file"
case "$state" in
  *'"state": "closed"'*|*'"state":"closed"'*) ;;
  *) exit 0 ;;
esac
reason=${state#*\"reason\"}
reason=${reason#*\"}
reason=${reason%%\"*}
case "$reason" in
  ""|*\*) reason="your request is still being checked" ;;
esac
printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"plumb: edits are on hold until the owner has answered: '"$reason"'. Run plumb clarify --wait, show the owner what it returns, and do not build until they have answered. This guard covers the edit tools only; edits made through the shell are not checked."}}'
exit 0
