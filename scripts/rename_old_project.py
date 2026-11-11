"""Apply the old-name -> IASO rename to a checked-out git tree (deterministic).

    python rename_tree.py ROOT CONVERT_PY

Moves every tracked path naming the old name, rewrites the text of every tracked text file,
then runs the records converter (CONVERT_PY, a copy of iaso/convert.py) on the tree so hashes,
pins and log digests follow. Leaves the result staged (``git add -A``) in ROOT."""
import os, subprocess, sys, shutil
from pathlib import Path

OLD = "plu" + "mb"
FORMS = ((OLD, "iaso"), (OLD.capitalize(), "Iaso"), (OLD.upper(), "IASO"))
OLD_DIR = "." + OLD


def rw(s):
    for a, b in FORMS:
        s = s.replace(a, b)
    return s


def git(root, *a):
    try:   # the tree's own helper once it has one; else the same filter locally
        from iaso.background import child_env
        env = child_env()
    except ImportError:
        env = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")}
    return subprocess.run(["git", "-C", str(root), *a], check=True, capture_output=True, env=env).stdout


def main(root, convert_py):
    root = Path(root).resolve()
    files = [f for f in git(root, "ls-files", "-z").decode().split("\0") if f]
    # 1. text of every tracked text file outside the records folder
    for f in files:
        if f.split("/")[0] == OLD_DIR or f.endswith(".whl"):
            continue
        p = root / f
        if not p.is_file() or p.is_symlink():
            continue
        raw = p.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if "\0" in text:
            continue
        new = rw(text)
        if new != text:
            p.write_bytes(new.encode("utf-8"))
    # 2. paths outside the records folder
    for f in files:
        if f.split("/")[0] == OLD_DIR:
            continue
        g = rw(f)
        if g != f:
            (root / g).parent.mkdir(parents=True, exist_ok=True)
            os.replace(root / f, root / g)
    # empty old directories left behind
    for d in sorted((p for p in root.rglob("*") if p.is_dir() and ".git" not in p.parts), key=lambda q: -len(q.parts)):
        if not any(d.iterdir()):
            d.rmdir()
    # 3. records: the converter, from the tree's own (renamed) code plus the converter file
    dst = root / "src" / "iaso" / "convert.py"
    had = dst.exists()
    shutil.copy(convert_py, dst)
    code = ("import sys; from pathlib import Path; from iaso.convert import convert; "
            "print(*convert(Path(sys.argv[1])), sep='\\n')")
    env = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")}
    env["PYTHONPATH"] = str(root / "src")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if (root / OLD_DIR).exists():
        subprocess.run([sys.executable, "-c", code, str(root)], check=True, env=env)
    if not had:
        dst.unlink()
    git(root, "add", "-A")


if __name__ == "__main__":
    main(*sys.argv[1:3])
