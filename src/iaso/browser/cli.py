"""Launch the study room."""

import argparse
import sys
import webbrowser
from pathlib import Path

from iaso.mod.session import Refused, refuse_under_marker


def run(command, argv):
    parser = argparse.ArgumentParser(prog="iaso ui", description="Local owner issue workspace")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", dest="open_browser")
    parser.add_argument("--assets", type=Path, help="Directory containing the built index.html")
    # the band's press (iaso.browser.launch) hands the capability on stdin, never in argv
    parser.add_argument("--token-stdin", action="store_true", help=argparse.SUPPRESS)
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    server = None
    try:
        refuse_under_marker("ui")
        from iaso.browser.server import make_server
        from iaso.browser.service import BrowserService
        from iaso.paths import find_root

        if not 0 <= args.port <= 65535:
            raise ValueError("port must be between 0 and 65535")
        root = find_root(args.root or Path.cwd())
        assets = args.assets or Path(__file__).resolve().parent / "static"
        server = make_server(BrowserService(root), port=args.port, assets=assets,
                             token=sys.stdin.readline().strip() or None if args.token_stdin
                             else None)
        link = server.origin + "/#token=" + server.token
        # The launch capability is printed once to the owner's terminal; never request logs.
        print("Iaso: " + link, flush=True)
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
        print(f"iaso ui: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        pass
    finally:
        if server:
            server.server_close()
    return 0
