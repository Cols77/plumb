"""Real Plumb room on a throwaway project for the Playwright suite.

Never the owner's records: everything lives in a fresh temporary directory.
"""

import os
import shutil
import tempfile
import threading
from pathlib import Path

# Like tests/conftest.py, this test process drops the agent marker the host set for its
# shell; the shell variable itself stays, and plumb ui keeps refusing under it.
os.environ.pop("PLUMB_AGENT_SESSION", None)
from plumb import study  # noqa: E402
from plumb.browser.server import make_server  # noqa: E402
from plumb.browser.service import BrowserService  # noqa: E402
from plumb.commands import init_repo  # noqa: E402

root = Path(tempfile.mkdtemp(prefix="plumb-e2e-")) / "room"
init_repo(root)
# SR-293: studies drawn as Markdown with a mermaid diagram, and one whose diagram is broken
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
# SR-342: a room on its own copy of the bundle, which a test rebuilds under an open tab.
swap = Path(os.environ["PLUMB_E2E_SWAP"])
shutil.rmtree(swap, ignore_errors=True)
shutil.copytree(static, swap)
threading.Thread(target=make_server(BrowserService(root), port=8767, assets=swap,
                                    token="e2e-token").serve_forever, daemon=True).start()
make_server(BrowserService(root), port=8765, assets=static, token="e2e-token").serve_forever()
