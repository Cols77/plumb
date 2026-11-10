import http.client
import json
import threading

import pytest

pytestmark = pytest.mark.sr("SR-269")


@pytest.fixture
def server(tmp_path):
    from iaso.browser.server import make_server
    from iaso.browser.service import BrowserService

    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "index.html").write_text("<html>workspace</html>")
    (tmp_path / "private.html").write_text("private repository data")
    httpd = make_server(BrowserService(tmp_path), port=0, assets=assets, token="test-token")
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()
    thread.join()


def request(server, method, path, data=None, **headers):
    conn = http.client.HTTPConnection(*server.server_address, timeout=5)
    body = (
        data if isinstance(data, (bytes, str)) else json.dumps(data) if data is not None else None
    )
    conn.request(method, path, body, headers)
    response = conn.getresponse()
    result = (response.status, response.read(), dict(response.getheaders()))
    conn.close()
    return result


def auth(server):
    return {
        "Authorization": "Bearer test-token",
        "Origin": server.origin,
        "Content-Type": "application/json",
    }


def test_workspace_requires_capability_and_host(server):
    assert request(server, "GET", "/api/workspace")[0] == 401
    assert request(server, "GET", "/api/workspace", **auth(server))[0] == 200
    assert (
        request(server, "GET", "/api/workspace", **{**auth(server), "Host": "evil.test"})[0] == 403
    )
    assert (
        request(server, "GET", "/api/workspace", **{**auth(server), "Origin": "http://evil.test"})[
            0
        ]
        == 403
    )


def test_posts_require_exact_origin_and_json_object(server):
    headers = auth(server)
    del headers["Origin"]
    assert request(server, "POST", "/api/understanding", {}, **headers)[0] == 403
    assert request(server, "POST", "/api/understanding", "{broken", **auth(server))[0] == 400
    assert request(server, "POST", "/api/understanding", [], **auth(server))[0] == 400
    assert (
        request(
            server,
            "POST",
            "/api/understanding",
            {},
            **{**auth(server), "Content-Type": "text/plain"},
        )[0]
        == 415
    )


def test_bounded_body_and_safe_routes(server):
    assert request(server, "POST", "/api/understanding", "x" * 70000, **auth(server))[0] == 413
    assert request(server, "GET", "/../private.html")[0] == 404
    assert request(server, "GET", "/%2e%2e/private.html")[0] == 404
    assert request(server, "GET", "/private.html")[0] == 404
    status, body, headers = request(server, "GET", "/")
    assert status == 200 and b"workspace" in body
    assert "Content-Security-Policy" in headers
    assert "img-src 'self' data: blob:" in headers["Content-Security-Policy"]
    assert "font-src 'self'" in headers["Content-Security-Policy"]
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Cache-Control"] == "no-store"


def test_token_never_appears_in_logs(server, capsys):
    request(server, "GET", "/?token=test-token")
    assert "test-token" not in capsys.readouterr().err
