"""Real Plumb server on a throwaway demo project for the Playwright suite.

Never the owner's records: everything lives in a fresh temporary directory. Each session
named below is a copy of the demo session, so one test's decisions never touch another's.
"""

import dataclasses
import os
import shutil
import tempfile
from pathlib import Path

# Like tests/conftest.py, this test process drops the agent marker the host set for its
# shell; the shell variable itself stays, and plumb ui keeps refusing under it.
os.environ.pop("PLUMB_AGENT_SESSION", None)
from plumb.api import open_core  # noqa: E402
from plumb.browser.demo import SESSION, seed  # noqa: E402
from plumb.browser.server import make_server  # noqa: E402
from plumb.browser.service import BrowserService  # noqa: E402
from plumb.mergedriver import conflicts  # noqa: E402
from plumb.understand import cards as card_shapes  # noqa: E402
from plumb.understand import cardstore, files, summary  # noqa: E402

root = seed(Path(tempfile.mkdtemp(prefix="plumb-e2e-")) / "demo")
sessions = root / ".plumb/session"
for name in ("e2e-trial", "e2e-choice", "e2e-choice-json", "e2e-conflict", "e2e-duplicate",
             "e2e-stale"):
    shutil.copytree(sessions / SESSION, sessions / name)
cards = {card.id: card for card in cardstore.own_cards(root, SESSION)}
second = dataclasses.replace(cards["demo-card-5"].questions[0], id="second")
cardstore.save(root, "multi-question", [dataclasses.replace(
    cards["demo-card-1"], id="multi-card", diagram="diagrams/missing.html",
    questions=(cards["demo-card-1"].questions[0], second))])
# A conflict resolves once per project, so "Keep the other" gets a second conflict.
requirements = root / ".plumb/requirements"
(requirements / "SR-007.md").write_text(
    (requirements / "SR-006.md").read_text(encoding="utf-8")
    .replace("SR-006", "SR-007").replace("IC-001", "IC-002"), encoding="utf-8")
core = open_core(root)
other = card_shapes.conflict_card(core.index(), conflicts.find(core, "IC-002"))
files.write_json_atomic(files.session_dir(root, "e2e-conflict-other") / summary.DRAWN,
                        [summary._drawn_entry(core, "e2e-conflict-other", other, "open",
                                              turn_built=True)])
(sessions / "empty-session").mkdir()
static = Path(__file__).resolve().parents[3] / "src/plumb/browser/static"
make_server(BrowserService(root, demo=True), port=8765, assets=static,
            token="e2e-token").serve_forever()
