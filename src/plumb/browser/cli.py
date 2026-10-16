"""Launch the local owner's browser workspace."""

import argparse
import sys
import tempfile
import webbrowser
from pathlib import Path

from plumb.mod.session import Refused, refuse_under_marker


def run(command, argv):
    parser = argparse.ArgumentParser(prog="plumb ui", description="Local owner issue workspace")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", dest="open_browser")
    parser.add_argument("--demo", action="store_true", help="Use an isolated temporary demo")
    parser.add_argument("--assets", type=Path, help="Directory containing the built index.html")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    temporary = None
    server = None
    try:
        refuse_under_marker("ui")
        from plumb.browser.server import make_server
        from plumb.browser.service import BrowserService
        from plumb.paths import find_root

        if not 0 <= args.port <= 65535:
            raise ValueError("port must be between 0 and 65535")
        if args.demo:
            from plumb.browser.demo import seed

            temporary = tempfile.TemporaryDirectory(prefix="plumb-browser-demo-")
            root = seed(Path(temporary.name))
        else:
            root = find_root(args.root or Path.cwd())
        assets = args.assets or Path(__file__).resolve().parent / "static"
        server = make_server(BrowserService(root, demo=args.demo), port=args.port, assets=assets)
        link = server.origin + "/#token=" + server.token
        # The launch capability is printed once to the owner's terminal; never request logs.
        print(("DEMO — isolated temporary project\n" if args.demo else "") + "Plumb: " + link)
        if not (assets / "index.html").is_file():
            print(
                "Browser assets missing. Build the browser app or pass --assets PATH; "
                "the API is available.",
                file=sys.stderr,
            )
        if args.open_browser:
            webbrowser.open(link)
        server.serve_forever()
    except Refused as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except (OSError, ValueError) as exc:
        print(f"plumb ui: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        pass
    finally:
        if server:
            server.server_close()
        if temporary:
            temporary.cleanup()
    return 0
