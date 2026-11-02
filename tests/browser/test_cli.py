import pytest

from plumb import cli

pytestmark = pytest.mark.sr("SR-269")


def test_cli_help_routes_to_browser(capsys):
    assert cli.main(["ui", "--help"]) == 0
    text = capsys.readouterr().out
    assert "--port" in text and "--assets" in text


def test_agent_guard_blocks_ui_launch():
    from plumb.guard import denied_command

    assert denied_command("plumb ui")


def test_cli_uses_packaged_static_assets(monkeypatch, repo):
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
    assert cli.main(["ui", "--root", str(repo)]) == 0
    assert held["assets"].name == "static"
    assert held["assets"].parent.name == "browser"


def test_cli_marker_refusal_does_not_clear_marker(monkeypatch, capsys):
    monkeypatch.setenv("PLUMB_AGENT_SESSION", "agent")
    assert cli.main(["ui"]) == 3
    import os

    assert os.environ["PLUMB_AGENT_SESSION"] == "agent"
