"""SR-345: the scripted owner answers from the hidden brief and sees no repository file."""

import json

import pytest

from iaso.contracts import DispatchError
from iaso.evaluate.owner import OWNER_SCHEMA, ScriptedOwner

BRIEF = "The board is 3 by 3, always."


class Double:
    def __init__(self, answer=None, error=None):
        self.answer, self.error, self.calls = answer, error, []

    def run(self, job, *, system, user, schema, on_step):
        self.calls.append((job, system, user, schema))
        if self.error:
            raise self.error
        return self.answer


@pytest.mark.sr("SR-345")
def test_reply_asking_gets_the_brief_answer():
    double = Double({"asks": True, "answer": "3 by 3."})
    got = ScriptedOwner(dispatcher=double).answer(BRIEF, "Build it", "How big is the board?")
    assert got == {"asks": True, "answer": "3 by 3."}
    assert double.calls[0][0].kind == "owner" and double.calls[0][3] == OWNER_SCHEMA


@pytest.mark.sr("SR-345")
def test_system_holds_brief_user_holds_request_and_reply(tmp_path):
    (tmp_path / "game.py").write_text("print(1)")
    double = Double({"asks": False, "answer": ""})
    ScriptedOwner(dispatcher=double).answer(BRIEF, "Build it", "Done.")
    _, system, user, _ = double.calls[0]
    assert BRIEF in system and BRIEF not in user
    assert json.loads(user) == {"request": "Build it", "reply": "Done."}
    assert str(tmp_path) not in system + user and "game.py" not in system + user


@pytest.mark.sr("SR-345")
def test_dispatch_error_answers_silence_and_is_noted():
    owner = ScriptedOwner(dispatcher=Double(error=DispatchError("run", "boom")))
    assert owner.answer(BRIEF, "r", "q?") == {"asks": False, "answer": ""}
    assert "boom" in owner.notes[0]
