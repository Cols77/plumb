from plumb.hosts.claude_code.pretool import incomplete_question


def test_judge_recommended_colon_reason_is_complete():
    q = {"questions": [{"question": "When?", "options": [
        {"label": "Now (Recommended)", "description": "Recommended: it avoids a stale read."},
        {"label": "Later", "description": "Waits for the next turn."}]}]}
    assert incomplete_question(q) == ""


def test_recommended_without_reason_still_refused():
    q = {"questions": [{"question": "When?", "options": [
        {"label": "Now (Recommended)", "description": "Recommended:"}]}]}
    assert incomplete_question(q) != ""
