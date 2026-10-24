"""Fixtures of the evaluate tests: reference programs the hidden checks must pass."""

import pytest

GAME = '''\
LINES = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]
score = {"X": 0, "O": 0}
def show(b):
    for i in (0, 3, 6):
        print(" ".join(b[i:i + 3]))
def main():
    while True:
        b, p = ["."] * 9, "X"
        while True:
            try:
                s = input(p + ": ")
            except EOFError:
                return
            if s == "":
                return
            if not (s.isdigit() and 1 <= int(s) <= 9 and b[int(s) - 1] == "."):
                print("invalid")
                continue
            b[int(s) - 1] = p
            show(b)
            if any(all(b[i] == p for i in ln) for ln in LINES):
                print(p + " wins")
                score[p] += 1
                break
            if "." not in b:
                print("draw")
                break
            p = "O" if p == "X" else "X"
        print("score X %d O %d" % (score["X"], score["O"]))
main()
'''

EXPENSES = '''\
import csv, os, sys
from collections import defaultdict
D = os.path.dirname(os.path.abspath(__file__))
E, B = os.path.join(D, "expenses.csv"), os.path.join(D, "budgets.csv")
def rows(path):
    return list(csv.reader(open(path, encoding="utf-8"))) if os.path.exists(path) else []
def put(path, row):
    with open(path, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(row)
def total(month, cat):
    return sum(int(r[2]) for r in rows(E) if r[0].startswith(month) and r[1] == cat)
a = sys.argv[1:]
if a[0] == "add":
    if not a[3].lstrip("-").isdigit():
        print("invalid amount")
        sys.exit(1)
    put(E, [a[1], a[2], a[3], " ".join(a[4:])])
    budget = dict(rows(B))
    if a[2] in budget and total(a[1][:7], a[2]) > int(budget[a[2]]):
        print("over budget: " + a[2])
elif a[0] == "list":
    for r in rows(E):
        print(" ".join(r))
elif a[0] == "report":
    t = defaultdict(int)
    for r in rows(E):
        if r[0].startswith(a[1]):
            t[r[1]] += int(r[2])
    for c in sorted(t):
        print(c, t[c])
    print("total", sum(t.values()))
elif a[0] == "budget":
    if not a[2].isdigit():
        print("invalid amount")
        sys.exit(1)
    put(B, [a[1], a[2]])
elif a[0] == "import":
    for r in csv.DictReader(open(a[1], encoding="utf-8")):
        if int(r["Amount"]) < 0:
            d, m, y = r["Date"].split("/")
            put(E, [f"{y}-{m}-{d}", "bank", str(-int(r["Amount"])), r["Description"]])
'''


@pytest.fixture
def reference_game() -> str:
    return GAME


@pytest.fixture
def reference_expenses() -> str:
    return EXPENSES
