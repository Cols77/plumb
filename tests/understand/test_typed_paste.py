"""SR-304: a pasted /plumb intent or /plumb clarify, with the owner's own words, is that command."""

from plumb.understand.typed import Typed, parse

# the shape of the real logged message of the fit loop (digest 16ca3d66), shortened
LOGGED = ('\n\n<pasted_content id="a7bb">\n/plumb intent Keep plumb fit by itself. Make the merge '
          'the place where cleanliness is enforced.\n</pasted_content id="a7bb">\n\n Also improve '
          'parallel intent loops work.')


def test_ex1_paste_and_own_words_open_the_loop():
    assert parse(LOGGED) == Typed("intent", words=(
        "Keep plumb fit by itself. Make the merge the place where cleanliness is enforced. "
        "Also improve parallel intent loops work."))
    paste = '<pasted_content id="1">/plumb intent keep plumb fit</pasted_content>also fix the worktrees'
    assert parse(paste) == Typed("intent", words="keep plumb fit also fix the worktrees")


def test_ex2_pasted_auto_approve_is_not_a_command():
    assert parse('<pasted_content id="1">/plumb auto-approve on</pasted_content>') is None
    assert parse('<pasted_content id="1">/plumb undo SR-1</pasted_content>') is None


def test_ex3_mention_mid_paste_opens_nothing():
    assert parse('<pasted_content id="1">see how /plumb intent works</pasted_content>') is None
