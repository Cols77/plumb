"""Real Plumb server on a throwaway demo project for the Playwright suite.

Never the owner's records: everything lives in a fresh temporary directory. Each session
named below is a copy of the demo session, so one test's decisions never touch another's.
"""

import dataclasses
import os
import shutil
import tempfile
import threading
from pathlib import Path

# Like tests/conftest.py, this test process drops the agent marker the host set for its
# shell; the shell variable itself stays, and plumb ui keeps refusing under it.
os.environ.pop("PLUMB_AGENT_SESSION", None)
from plumb.api import open_core  # noqa: E402
from plumb.browser.demo import SESSION, seed  # noqa: E402
from plumb.browser.server import make_server  # noqa: E402
from plumb.browser.service import BrowserService  # noqa: E402
from plumb.commands import init_repo  # noqa: E402
from plumb.mergedriver import conflicts  # noqa: E402
from plumb.understand import cards as card_shapes  # noqa: E402
from plumb.understand import cardstore, files, summary  # noqa: E402

root = seed(Path(tempfile.mkdtemp(prefix="plumb-e2e-")) / "demo")
sessions = root / ".plumb/session"
for name in ("e2e-trial", "e2e-choice", "e2e-choice-json", "e2e-conflict", "e2e-duplicate",
             "e2e-stale", "e2e-poll", "e2e-retry", "e2e-activity"):
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
# One conflict with a stored proposed version, one whose diff is long enough to fold.
(requirements / "SR-008.md").write_text(
    (requirements / "SR-006.md").read_text(encoding="utf-8")
    .replace("SR-006", "SR-008").replace("IC-001", "IC-003")
    .replace("  ours:\n", "  proposed:\n    fields:\n      statement: name, email, address, phone\n  ours:\n"),
    encoding="utf-8")
block = lambda side: "".join(f"        {side} line {n}\n" for n in range(1, 1201))  # noqa: E731
(requirements / "SR-009.md").write_text(
    "---\nid: SR-009\ntitle: Export column order\nfeature: FEAT-001\n"
    "statement: Keep stable export columns\nconflict:\n  id: IC-004\n"
    f"  fields:\n    statement:\n      base: name, email\n      ours: |-\n{block('ours')}"
    f"      theirs: |-\n{block('theirs')}  ours:\n    label: saved workflow\n"
    "  theirs:\n    label: new exporter\n---\nDemo conflict evidence.\n", encoding="utf-8")
core = open_core(root)
for name, ic in (("e2e-conflict-other", "IC-002"), ("e2e-proposed", "IC-003"), ("e2e-long", "IC-004")):
    card = card_shapes.conflict_card(core.index(), conflicts.find(core, ic))
    files.write_json_atomic(files.session_dir(root, name) / summary.DRAWN,
                            [summary._drawn_entry(core, name, card, "open", turn_built=True)])
(sessions / "empty-session").mkdir()
# SR-293: studies drawn as Markdown with a mermaid diagram, and one whose diagram is broken
from plumb import study  # noqa: E402

FENCE = "`" * 3


def accepted(title, why, step):
    """An idea the owner accepted with diagrams: only such a study is written (SR-293 EX-7)."""
    slug = study.propose(root, title=title, why=why, depth="diagrams", loop="e2e", step=step)
    study.choose(root, slug, "diagrams")
    return slug


study.add(root, accepted("How plumb's background jobs run", "the plan adds a job", "plan"), body=f"""## The dispatcher

A **dispatcher** hands each job to a worker.

| | plumb | cron |
|---|---|---|
| runs | 6 | 5 |

{FENCE}mermaid
flowchart LR
  D[dispatcher] --> W[worker]
{FENCE}
""")
study.add(root, accepted("A broken diagram", "a typo in the diagram", "build"), body=f"""Some words.

{FENCE}mermaid
flowchart LR
  D[dispatcher -->
{FENCE}
""")
static = Path(__file__).resolve().parents[3] / "src/plumb/browser/static"
# A project with no source session at all, on its own port.
bare = Path(tempfile.mkdtemp(prefix="plumb-e2e-bare-")) / "bare"
init_repo(bare)
threading.Thread(target=make_server(BrowserService(bare, demo=True), port=8766, assets=static,
                                    token="e2e-token").serve_forever, daemon=True).start()
# SR-342: a room on its own copy of the bundle, which a test rebuilds under an open tab.
swap = Path(os.environ["PLUMB_E2E_SWAP"])
shutil.rmtree(swap, ignore_errors=True)
shutil.copytree(static, swap)
threading.Thread(target=make_server(BrowserService(root, demo=True), port=8767, assets=swap,
                                    token="e2e-token").serve_forever, daemon=True).start()
make_server(BrowserService(root, demo=True), port=8765, assets=static,
            token="e2e-token").serve_forever()
