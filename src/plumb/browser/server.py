"""Loopback-only HTTP transport. The capability never enters URLs sent to this server."""

import hmac
import json
import mimetypes
import re
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

MAX_BODY = 65536


def make_server(service, *, port=0, assets=None, token=None):
    """Bind IPv4 loopback; callers cannot select a public listening address."""
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.service = service
    server.assets = Path(assets).resolve() if assets else None
    server.token = token or secrets.token_urlsafe(32)
    server.origin = f"http://127.0.0.1:{server.server_address[1]}"
    server.expected_host = server.origin.removeprefix("http://")
    return server


class Handler(BaseHTTPRequestHandler):
    server_version = "PlumbBrowser"

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *_args):
        # Paths, query strings, fragments pasted by mistake and headers can contain secrets.
        pass

    def _send(self, status, data, mime="application/json; charset=utf-8"):
        body = (
            json.dumps(data, ensure_ascii=False).encode("utf-8") if isinstance(data, dict) else data
        )
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; "
            "connect-src 'self'; frame-src 'self'; base-uri 'none'; "
            "form-action 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status, message):
        self._send(status, {"error": message})

    def _guard(self, *, api=False):
        if self.headers.get_all("Host") != [self.server.expected_host]:
            self._error(403, "Host does not match the local workspace")
            return False
        origins = self.headers.get_all("Origin")
        if (origins is not None and origins != [self.server.origin]) or (
            self.command == "POST" and origins != [self.server.origin]
        ):
            self._error(403, "Origin does not match the local workspace")
            return False
        if api and not hmac.compare_digest(
            self.headers.get("Authorization", ""), "Bearer " + self.server.token
        ):
            self._error(401, "Open the workspace using its launch link")
            return False
        return True

    def do_GET(self):
        self._dispatch()

    def do_POST(self):
        self._dispatch()

    def _dispatch(self):
        try:
            url = urlsplit(self.path)
            path = unquote(url.path, errors="strict")
            if url.scheme or url.netloc or "\\" in path or "\x00" in path:
                self._error(404, "Unknown route")
                return
            api = path.startswith("/api/")
            if not self._guard(api=api):
                return
            if not api:
                if self.command != "GET":
                    self._error(405, "Method not allowed")
                    return
                self._static(path)
                return
            payload = {}
            if self.command == "POST":
                if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                    self._error(415, "Expected application/json")
                    return
                lengths = self.headers.get_all("Content-Length") or []
                if self.headers.get("Transfer-Encoding") or len(lengths) != 1:
                    self._error(400, "Expected one Content-Length")
                    return
                length = int(lengths[0])
                if length < 0 or length > MAX_BODY:
                    self._error(413, "Request body too large")
                    return
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError("Incomplete request body")
                payload = json.loads(raw.decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("Expected a JSON object")
            if self.command == "GET" and path == "/api/workspace":
                self._send(200, self.server.service.workspace())
                return
            service = self.server.service
            if path == "/api/studies" and self.command == "GET":
                self._send(200, service.studies())
                return
            if path == "/api/understanding" and self.command == "POST":
                self._send(200, service.save_understanding(payload))
                return
            match = re.fullmatch(r"/api/studies/([A-Za-z0-9][A-Za-z0-9-]{0,79})/(open|mark)", path)
            if match and self.command == "POST":
                slug, action = match.groups()
                self._send(
                    200, service.open_study(slug) if action == "open"
                    else service.mark_study(slug, payload)
                )
                return
            match = re.fullmatch(r"/api/sessions/([A-Za-z0-9_-]+)/(draw|press|diagram)", path)
            if not match:
                self._error(404, "Unknown route")
                return
            session, action = match.groups()
            if self.command == "POST" and action == "draw":
                result = self.server.service.draw(session)
            elif self.command == "POST" and action == "press":
                result = self.server.service.press(session, payload)
            elif self.command == "GET" and action == "diagram":
                values = parse_qs(url.query).get("card", [])
                if len(values) != 1:
                    raise ValueError("Expected one card id")
                result = self.server.service.diagram(session, values[0])
            else:
                self._error(405, "Method not allowed")
                return
            self._send(200, result)
        except PermissionError as exc:
            self._error(409, str(exc))
        except LookupError as exc:
            self._error(404, str(exc))
        except (ValueError, UnicodeError) as exc:
            self._error(400, str(exc))
        except (TimeoutError, ConnectionError):
            self.close_connection = True
        except Exception:  # noqa: BLE001 - never expose traceback, paths or capability
            self._error(500, "Workspace operation failed; refresh and inspect the source session")

    def _static(self, path):
        base = self.server.assets
        relative = "index.html" if path == "/" else path.lstrip("/")
        if ".." in relative.split("/") or (path != "/" and not path.startswith("/assets/")):
            self._error(404, "Unknown asset")
            return
        if base is None:
            self._error(
                503, "Browser assets are missing. Build the browser app or pass --assets PATH."
            )
            return
        target = (base / relative).resolve()
        if not target.is_relative_to(base) or not target.is_file():
            self._error(404, "Unknown asset")
            return
        mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if target.suffix.lower() in (".js", ".mjs"):
            mime = "text/javascript"
        self._send(200, target.read_bytes(), mime)
