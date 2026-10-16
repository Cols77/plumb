import pytest

from plumb import cli

pytestmark = pytest.mark.sr("SR-176")


def test_cli_help_routes_to_browser(capsys):
    assert cli.main(["ui", "--help"]) == 0
    text = capsys.readouterr().out
    assert "--demo" in text and "--port" in text and "--assets" in text


def test_agent_guard_blocks_ui_launch():
    from plumb.guard import denied_command

    assert denied_command("plumb ui --demo")


def test_cli_uses_packaged_static_assets(monkeypatch):
    from plumb.browser import server

    held = {}

    class StubServer:
        origin = "http://127.0.0.1:8765"
        token = "demo-test-token"

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            pass

    def make_server(service, **options):
        held.update(options)
        return StubServer()

    monkeypatch.setattr(server, "make_server", make_server)
    assert cli.main(["ui", "--demo"]) == 0
    assert held["assets"].name == "static"
    assert held["assets"].parent.name == "browser"


def test_demo_creates_real_isolated_cases(tmp_path):
    from plumb.browser.demo import seed
    from plumb.browser.service import BrowserService

    root = tmp_path / "demo"
    seed(root)
    ui = BrowserService(root, demo=True)
    assert ui.workspace()["project"]["demo"] is True
    snap = ui.draw("demo-session")
    states = {c["state"] for c in snap["cards"]}
    assert {"waiting", "blocked", "done", "left_open"} <= states
    assert any(c["content"] and c["offers"] for c in snap["cards"])
    assert {"trial", "choice", "conflict"} <= {c["kind"] for c in snap["cards"]}
    diagram = next(c for c in snap["cards"] if c["diagram"]["available"])
    assert "<svg" in ui.diagram("demo-session", diagram["id"])["text"]


def test_cli_marker_refusal_does_not_clear_marker(monkeypatch, capsys):
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "agent")
    assert cli.main(["ui", "--demo"]) == 3
    import os

    assert os.environ["PLUMB_AGENT_SESSION"] == "agent"
