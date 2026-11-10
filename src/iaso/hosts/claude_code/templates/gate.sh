#!/bin/sh
# iaso: the check before an edit tool runs (SR-103). Shell only: no interpreter, no other program,
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
# a card's diagram is drawn while the card is open (SR-146): its folder is let through (JSON doubles a Windows backslash, hence the stars)
path=${input#*\"file_path\"}
path=${path#*\"}
path=${path%%\"*}
case "$path" in
  *..*) ;;
  *.iaso[/\\]*session[/\\]*diagrams[/\\]*) exit 0 ;;
esac
session=${input#*\"session_id\"}
session=${session#*\"}
session=${session%%\"*}
case "$session" in
  ""|*[!A-Za-z0-9_-]*) exit 0 ;;
esac
# the records folder (.iaso/) of IASO_ROOT (the plugin hook
# passes the one its walk up found, so a session started in a subfolder is gated too), else of
# the project folder (the per-repository install)
r="${IASO_ROOT:-${CLAUDE_PROJECT_DIR:-.}}"
sd=.iaso
file="$r/$sd/session/$session/gate"
if [ -z "$IASO_ROOT" ] && [ ! -r "$file" ]; then
  # the per-repository install passes no IASO_ROOT: a session started in a subfolder reads
  # the gate of the records folder above it, the walk stopping at the git root
  d=${CLAUDE_PROJECT_DIR:-$PWD}
  while :; do
    case $d in
      *\\*) d="${d%%\\*}/${d#*\\}" ;;
      *) break ;;
    esac
  done
  while [ -n "$d" ]; do
    sd=.iaso
    if [ -d "$d/$sd/session" ]; then
      file="$d/$sd/session/$session/gate"
      break
    fi
    [ -e "$d/.git" ] && break
    parent=${d%/*}
    [ "$parent" = "$d" ] && break
    d=$parent
  done
fi
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
printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"iaso: edits are on hold until the owner has answered: '"$reason"'. Run iaso clarify --wait, show the owner what it returns, and do not build until they have answered. This guard covers the edit tools only; edits made through the shell are not checked."}}'
exit 0
