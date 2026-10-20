"""Serialized, fresh-core browser operations against original source sessions."""

import dataclasses
import re
import secrets
import threading
from pathlib import Path

from plumb import study
from plumb.api import open_core
from plumb.browser import followup
from plumb.browser import session as registration
from plumb.mod import offers
from plumb.mod.press import Unknown, press
from plumb.mod.session import now, refuse_under_marker
from plumb.understand import cardstore, files


class BrowserService:
    def __init__(self, root: Path, *, demo=False):
        refuse_under_marker("browser startup")
        self.root = Path(root).resolve()
        self.demo = demo
        self.lock = threading.RLock()
        self._keys = {}
        for session in self.sessions():
            followup.recover(self.root, session)

    def sessions(self):
        base = self.root / ".plumb/session"
        return (
            sorted(
                p.name
                for p in base.iterdir()
                if p.is_dir() and not p.is_symlink() and re.fullmatch(r"[A-Za-z0-9_-]+", p.name)
            )
            if base.is_dir()
            else []
        )

    def _session(self, session):
        if session not in self.sessions():
            raise LookupError("Unknown source session")

    def _key(self, core, session):
        if session not in self._keys:
            self._keys[session] = secrets.token_hex(32)
            registration.hello(core, session, self._keys[session])
        return self._keys[session]

    def workspace(self):
        with self.lock:
            core = open_core(self.root)
            sessions = []
            for name in self.sessions():
                states = cardstore.states(core, name)
                counts = {
                    s: sum(v[0] == s for v in states.values())
                    for s in ("waiting", "processing", "blocked", "done", "left_open")
                }
                if not any(counts.values()):
                    continue  # a session that never drew a card is noise in the selector
                sessions.append({"id": name, "counts": counts})
            return {
                "project": {"name": self.root.name, "root": str(self.root), "demo": self.demo},
                "sessions": sessions,
            }

    def draw(self, session):
        with self.lock:
            self._session(session)
            core = open_core(self.root)
            key = self._key(core, session)
            cards = offers.drawn_cards(
                core, session, registration.key_digest(key), surface="browser"
            )
            cards += offers.settled_cards(core, session)
            index = core.index()
            statuses = core.status()
            for card in cards:
                state = cardstore.card_from_json(card)
                if card.get("content") is None:
                    card["content"] = offers.content_for(core, session, state)
                ids = {q.record for q in state.questions if q.record}
                for offer in card["offers"]:
                    stored = offers.load_offer(
                        self.root, session, offer["offer_id"], surface="browser"
                    )
                    ids.update(r["id"] for r in stored.get("records", []))
                card["records"] = [
                    {
                        "id": rid,
                        "title": index[rid].title,
                        "hash": index[rid].hash,
                        "body": index[rid].body,
                        "fields": dict(index[rid].fields),
                        "status": dataclasses.asdict(statuses[rid]),
                    }
                    for rid in sorted(ids)
                    if rid in index
                ]
                card["diff"] = None
                for record in card["records"]:
                    conflict = record["fields"].get("conflict")
                    if isinstance(conflict, dict):
                        card["diff"] = {
                            "record": record["id"],
                            "fields": conflict.get("fields", {}),
                            "labels": {
                                s: conflict.get(s, {}).get("label", s) for s in ("ours", "theirs")
                            },
                            "proposed": conflict.get("proposed"),
                        }
                        break
                from plumb.browser import diagrams

                diagram = diagrams.read(self.root, state.diagram)
                card["diagram"] = {
                    "source": state.diagram,
                    "available": diagram["text"] is not None,
                    "error": diagram["error"],
                }
            return {
                "session": session,
                "cards": cards,
                "followups": followup.history(self.root, session),
            }

    # Studies and the understanding picture (DEC-151): a section beside the questions. Its
    # buttons correct the picture only; nothing reaches a session as an answer (DEC-152).
    def studies(self):
        with self.lock:
            return {
                "studies": [
                    {k: v for k, v in s.items() if k != "body"} for s in study.studies(self.root)
                    if s["status"] in study.WRITTEN    # an idea has no page (DEC-207)
                ],
                "understanding": self._understanding(),
            }

    def _understanding(self):
        return {"text": study.picture_text(self.root), **study.picture(self.root)}

    def open_study(self, slug):
        """The owner reads a study: it is opened, and the band's study line goes (SR-294)."""
        with self.lock:
            return study.mark(self.root, slug, "opened")

    def mark_study(self, slug, payload):
        how = payload.get("mark")
        if how not in ("known", "deeper"):
            raise ValueError("mark must be known or deeper")
        with self.lock:
            marked = study.mark(self.root, slug, how)
            return {"study": marked, "understanding": self._understanding()}

    def save_understanding(self, payload):
        with self.lock:
            study.save_picture(self.root, payload.get("text"))
            return self._understanding()

    def diagram(self, session, card_id):
        from plumb.browser import diagrams

        with self.lock:
            self._session(session)
            card = next(
                (c for c in cardstore.load(self.root, session, open_only=False) if c.id == card_id),
                None,
            ) or offers.turn_card(self.root, session, card_id)
            if card is None:
                raise LookupError("Unknown card in this source session")
            return diagrams.read(self.root, card.diagram)

    def press(self, session, payload):
        with self.lock:
            self._session(session)
            offer, choice, request_id = (payload.get(k) for k in ("offer", "choice", "request_id"))
            text = payload.get("text", "")
            if not isinstance(offer, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", offer):
                raise ValueError("offer must name a drawn offer")
            if type(choice) is not int or choice < 0:
                raise ValueError("choice must be a nonnegative integer")
            if not isinstance(request_id, str) or not re.fullmatch(
                r"[A-Za-z0-9_-]{1,128}", request_id
            ):
                raise ValueError("request_id must be 1-128 letters, digits, underscores or hyphens")
            if not isinstance(text, str) or len(text) > 16000:
                raise ValueError("text must contain at most 16000 characters")
            fingerprint = files.digest_of([offer, choice, text])
            held = followup.read(self.root, session, request_id)
            if held:
                if held["fingerprint"] != fingerprint:
                    raise ValueError("request_id was already used for another answer")
                if held.get("result"):
                    original = followup.read(self.root, session, held.get("alias_of", request_id))
                    original = original or held
                    return {
                        **held["result"],
                        "duplicate": True,
                        "followup": {"id": original["id"], "status": original["status"]},
                    }
                raise ValueError(
                    "This request was interrupted; refresh to inspect the recorded answer"
                )
            core = open_core(self.root)
            key = self._key(core, session)
            drawn = offers.load_offer(self.root, session, offer, surface="browser")
            if not drawn:
                raise PermissionError("No such offer was drawn in this source session")
            if choice >= len(drawn.get("buttons") or ()):
                raise Unknown(f"plumb mod press: the card has no button {choice}", 2)
            current = next(
                (
                    c
                    for c in cardstore.load(self.root, session, open_only=False)
                    if c.id == drawn["card"]
                ),
                None,
            )
            if current and current.kind == "stale_link" and drawn.get(
                "presentation"
            ) != offers.presentation_digest(core, session, current):
                raise PermissionError(
                    "The card changed since it was shown. Refresh it before answering."
                )
            latest = next(
                (
                    e.payload
                    for e in reversed(core.events())
                    if e.kind == "card-press"
                    and e.payload.get("session") == session
                    and e.payload.get("card") == drawn["card"]
                ),
                {},
            )
            for previous in followup.directory(self.root, session).glob("*.json"):
                done = files.read_json(previous)
                if (
                    isinstance(done, dict)
                    and done.get("fingerprint") == fingerprint
                    and done.get("result")
                    and latest.get("request_id") == done.get("id")
                ):
                    followup.write(
                        self.root,
                        session,
                        {
                            "id": request_id,
                            "alias_of": done["id"],
                            "fingerprint": fingerprint,
                            "status": "duplicate",
                            "result": done["result"],
                            "created": now(),
                        },
                    )
                    return {
                        **done["result"],
                        "duplicate": True,
                        "followup": {"id": done["id"], "status": done["status"]},
                    }
            if current and any(a.question == drawn["question"] for a in current.answers):
                raise PermissionError("This question was already answered; refresh the card")
            # Intent is durable before any answer side effect. An interrupted intent is
            # never replayed blindly, which could repeat a conflict application.
            entry = {
                "id": request_id,
                "card": drawn["card"],
                "created": now(),
                "sequence": 1
                + max(
                    (e.get("sequence", 0) for e in followup.entries(self.root, session)), default=0
                ),
                "status": "pending",
                "fingerprint": fingerprint,
                "text": text,
                "offer": offer,
                "choice": choice,
            }
            followup.write(self.root, session, entry)
            try:
                result = press(
                    core,
                    session,
                    offer,
                    choice,
                    {"key": key, "request_id": request_id},
                    surface="browser",
                )
            except (PermissionError, Unknown):
                followup.write(self.root, session, {**entry, "status": "failed"})
                raise
            status = "queued" if result.get("model_note") else "not_needed"
            result.update(duplicate=False, followup={"id": request_id, "status": status})
            followup.write(
                self.root,
                session,
                {
                    **entry,
                    "status": status,
                    "result": result,
                    "model_note": result.get("model_note", ""),
                },
            )
            return result
