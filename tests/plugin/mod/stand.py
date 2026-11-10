"""Run the mod's tests from outside the shipped plugin (SR-123).

    python tests/plugin/mod/stand.py          # assemble the stand and run `claude plugin test`
    python tests/plugin/mod/stand.py --keep   # the same, and print where the stand is

The tests of iaso's mod (``*.test.tsx``, ``harness.ts``, ``fixtures.ts``) live here, beside
the Python tests, so a marketplace install of ``plugin/`` never carries them. ``claude plugin
test <dir>`` runs the tests under a mod's own folder and refuses imports from outside it, so this
assembles a stand in a temporary folder: the mod as it ships (``plugin/.claude-plugin``,
``plugin/hooks``, ``plugin/types``) at the stand's root, and this folder at the same place it
has in the repository (``tests/plugin/mod``, with ``plugin/types`` beside it), so the tests'
imports (``../../../plugin/types``) resolve in the stand as they do in an editor.
``tests/plugin/test_mod_stand.py`` runs it from pytest when ``claude`` is on the PATH."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PLUGIN = REPO / "plugin"
# what of the plugin the mod loads: its manifest, its hooks module and its $.state contract
MOD_PARTS = (".claude-plugin", "hooks", "types")


def _tests() -> list[Path]:
    return sorted(p for p in HERE.iterdir() if p.is_file() and p.suffix in (".ts", ".tsx"))


def assemble(root: Path) -> Path:
    """Lay the stand under ``root``; the folder ``claude plugin test`` takes."""
    for part in MOD_PARTS:
        src = PLUGIN / part
        ignore = shutil.ignore_patterns("types") if part == ".claude-plugin" else None
        shutil.copytree(src, root / part, ignore=ignore)
    # the tests where they sit in the repository, and the contract and hooks where they import
    # them from (a test may call a hooks helper such as findPress directly)
    for part in ("types", "hooks"):
        shutil.copytree(PLUGIN / part, root / "plugin" / part)
    dest = root / "tests" / "plugin" / "mod"
    dest.mkdir(parents=True)
    for path in _tests():
        shutil.copyfile(path, dest / path.name)
    return root


def run(claude: str = "claude", keep: bool = False) -> subprocess.CompletedProcess[str]:
    """Run the mod's tests in a fresh stand; the run's output is captured (stdout and stderr in
    one), so a caller can say which cases failed and why."""
    tmp = Path(tempfile.mkdtemp(prefix="iaso-mod-stand-"))
    try:
        stand = assemble(tmp / "iaso")
        if keep:
            print(f"stand: {stand}")
        return subprocess.run([claude, "plugin", "test", str(stand)], check=False, text=True,
                              encoding="utf-8", errors="replace", stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT)
    finally:
        if not keep:
            shutil.rmtree(tmp, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--keep", action="store_true", help="leave the stand and say where")
    parser.add_argument("--claude", default="claude", help="the claude binary to run")
    args = parser.parse_args(argv)
    done = run(args.claude, args.keep)
    print(done.stdout, end="")
    return done.returncode


if __name__ == "__main__":
    sys.exit(main())
