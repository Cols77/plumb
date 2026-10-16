"""Reproducible, labelled temporary demo made from real records and card shapes."""

import dataclasses
from pathlib import Path

from plumb.api import open_core
from plumb.commands import init_repo
from plumb.contracts import CARD_PRESS, Choice
from plumb.understand import cards as card_shapes
from plumb.understand import cardstore, files, summary, trial

SESSION = "demo-session"


def seed(root: Path):
    """Populate a fresh empty directory only. Never accepts an existing owner project."""
    root = Path(root)
    if root.exists() and any(root.iterdir()):
        raise ValueError("Demo seeding requires an empty directory")
    root.mkdir(parents=True, exist_ok=True)
    init_repo(root)
    (root / ".plumb/features/FEAT-001.md").write_text(
        "---\nid: FEAT-001\ntitle: Demo export workspace\n---\nIsolated browser demonstration.\n",
        encoding="utf-8",
    )
    titles = [
        "Keep exports readable",
        "Preserve the previous format",
        "Confirm the saved filter",
        "Choose when to send notifications",
        "Choose the export format",
    ]
    demo_ids = ("SR-001", "SR-002", "SR-003", "SR-004", "SR-005")  # fixed demo data, never reserved
    for sr, title in zip(demo_ids, titles):
        (root / ".plumb/requirements" / f"{sr}.md").write_text(
            f"---\nid: {sr}\ntitle: {title}\nfeature: FEAT-001\n"
            f"statement: {title}.\nexamples:\n- id: EX-1\n  given: an existing workspace\n"
            "  when: the owner returns\n  then: their saved choices remain available\n---\n"
            "Demonstration evidence only. This temporary project contains no owner work.\n",
            encoding="utf-8",
        )
    diagram = root / "diagrams/flow.html"
    diagram.parent.mkdir()
    diagram.write_text(
        """<!doctype html><html><body><svg xmlns="http://www.w3.org/2000/svg"
 viewBox="0 0 640 220"><rect width="640" height="220" fill="#f7f5ef"/>
 <rect x="30" y="70" width="160" height="70" rx="12" fill="#ccdce8"/>
 <text x="55" y="112" font-size="19">Saved rows</text>
 <path d="M190 105H250M410 105H470" stroke="#334" stroke-width="3"/>
 <rect x="250" y="70" width="160" height="70" rx="12" fill="#d7e4cf"/>
 <text x="273" y="112" font-size="19">CSV schema</text>
 <rect x="470" y="70" width="140" height="70" rx="12" fill="#ecddc5"/>
 <text x="488" y="112" font-size="19">Download</text>
 </svg></body></html>""",
        encoding="utf-8",
    )
    core = open_core(root)
    cards = []
    for n, sr in enumerate(demo_ids, 1):
        card = trial.card(core, trial.Candidate(core.index()[sr], 0.9, {}))
        if n == 5:
            question = dataclasses.replace(
                card.questions[0],
                text="Which format should exports use?",
                choices=(
                    Choice("Keep CSV", "accepted", consequence="Existing spreadsheets still open"),
                    Choice(
                        "Use JSON",
                        "change",
                        "Use JSON",
                        "Preserves nested values; spreadsheet users need an importer",
                    ),
                ),
            )
            card = dataclasses.replace(
                card,
                kind="choice",
                questions=(question,),
                issue="CSV preserves existing spreadsheet workflows.",
                evidence="Demo example: one saved row with a nested address.",
            )
        status = {2: "closed", 3: "closed", 4: "left_open"}.get(n, "open")
        cards.append(
            dataclasses.replace(
                card,
                id=f"demo-card-{n}",
                status=status,
                diagram="diagrams/flow.html" if n in (1, 5) else "",
            )
        )
    cardstore.save(root, SESSION, cards)
    conflict_path = root / ".plumb/requirements/SR-006.md"
    conflict_path.write_text(
        "---\nid: SR-006\ntitle: Export column order\nfeature: FEAT-001\n"
        "statement: Keep stable export columns\nconflict:\n  id: IC-001\n"
        "  fields:\n    statement:\n      base: name, email\n      ours: name, email, address\n"
        "      theirs: email, name\n  ours:\n    label: saved workflow\n"
        "  theirs:\n    label: new exporter\n---\nDemo conflict evidence.\n",
        encoding="utf-8",
    )
    from plumb.mergedriver import conflicts

    core = open_core(root)
    conflict = card_shapes.conflict_card(core.index(), conflicts.find(core, "IC-001"))
    files.write_json_atomic(
        files.session_dir(root, SESSION) / summary.DRAWN,
        [summary._drawn_entry(core, SESSION, conflict, "open", turn_built=True)],
    )
    # A genuine stale press history is what computes blocked; stored status remains closed.
    core.log_append(
        "events",
        CARD_PRESS,
        {
            "session": SESSION,
            "card": "demo-card-2",
            "question": cards[1].questions[0].id,
            "answer": "accepted",
            "stale": True,
            "record": "SR-002",
            "hash": "sha256:older-demo-version",
            "surface": "demo",
        },
    )
    return root
