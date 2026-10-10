"""The task registry every agent in this folder shares.

The user works with several AI agents on this project, in sessions that do not
see each other.  Without a shared record each one re-derives what is finished,
marks things done that were not, and loses the instructions given to a previous
session.  So the record lives in ``TASKS.md`` at the project root, and this tool
is how it is read and changed -- editing the table by hand is what makes the
format drift until nothing can parse it.

    python engine/tasks.py list                  everything, grouped by area
    python engine/tasks.py next                  what to pick up now
    python engine/tasks.py show  T-042
    python engine/tasks.py start T-042
    python engine/tasks.py done  T-042 "harness 84/84 on 12 samples"
    python engine/tasks.py block T-042 "needs the v1.4 subschema"
    python engine/tasks.py open  T-042 "regressed, see span_diff"
    python engine/tasks.py add   "Title" --area map --note "asked 2026-09-16"
    python engine/tasks.py ask   "Question for the user"

With other sessions working in parallel, ``add`` numbers from this branch's
own block (``python engine/agents.py init``) so ids never collide.

A task is never marked done without a note: the note is the evidence, and a
status with no evidence is how a registry stops being trustworthy.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "TASKS.md"

# The registry is UTF-8 and task titles carry arrows and dashes, but a Windows
# console defaults to cp1252 and raises rather than transliterating.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

STATUSES = ("done", "partial", "open", "blocked")
ORDER = {"blocked": 0, "partial": 1, "open": 2, "done": 3}
MARK = {"done": "[x]", "partial": "[~]", "open": "[ ]", "blocked": "[!]"}

ROW = re.compile(r"^\|\s*(T-\d+)\s*\|\s*(\w+)\s*\|\s*([\w/-]*)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|$")


@dataclass
class Task:
    task_id: str
    status: str
    area: str
    title: str
    note: str = ""

    def row(self) -> str:
        return f"| {self.task_id} | {self.status} | {self.area} | {self.title} | {self.note} |"

    def line(self) -> str:
        note = f"  --  {self.note}" if self.note else ""
        return f"  {MARK[self.status]} {self.task_id}  {self.area:<10} {self.title}{note}"


def load() -> tuple[list[str], list[Task]]:
    """The file's lines and the tasks parsed out of them."""
    if not REGISTRY.exists():
        raise SystemExit(f"no registry at {REGISTRY}; create TASKS.md first")
    lines = REGISTRY.read_text(encoding="utf-8").splitlines()
    tasks = []
    for line in lines:
        m = ROW.match(line.strip())
        if m and m.group(2) in STATUSES:
            tasks.append(Task(m.group(1), m.group(2), m.group(3),
                              m.group(4), m.group(5)))
    return lines, tasks


def save(lines: list[str], task: Task) -> None:
    """Write one task back into the line it came from."""
    for i, line in enumerate(lines):
        m = ROW.match(line.strip())
        if m and m.group(1) == task.task_id:
            lines[i] = task.row()
            break
    REGISTRY.write_text("\n".join(lines) + "\n", encoding="utf-8")


def find(tasks: list[Task], task_id: str) -> Task:
    key = task_id.upper()
    if not key.startswith("T-"):
        key = f"T-{int(key):03d}"
    for t in tasks:
        if t.task_id == key:
            return t
    raise SystemExit(f"no task {key}; run `tasks.py list`")


def _today() -> str:
    return _dt.date.today().isoformat()


# ------------------------------------------------------------------ commands
def cmd_list(args) -> int:
    _lines, tasks = load()
    if args.status:
        tasks = [t for t in tasks if t.status == args.status]
    if args.area:
        tasks = [t for t in tasks if t.area == args.area]
    areas: dict[str, list[Task]] = {}
    for t in tasks:
        areas.setdefault(t.area, []).append(t)
    for area in sorted(areas):
        print(f"\n{area.upper()}")
        for t in sorted(areas[area], key=lambda t: (ORDER[t.status], t.task_id)):
            print(t.line())
    print()
    summary(tasks)
    return 0


def cmd_next(args) -> int:
    _lines, tasks = load()
    live = [t for t in tasks if t.status in ("blocked", "partial", "open")]
    live.sort(key=lambda t: (ORDER[t.status], t.task_id))
    print("Pick up next (blocked first -- those need the user, so ask early):\n")
    for t in live[:args.count]:
        print(t.line())
    print()
    summary(tasks)
    return 0


def cmd_show(args) -> int:
    _lines, tasks = load()
    t = find(tasks, args.task_id)
    print(f"{t.task_id}   {t.status.upper()}   [{t.area}]")
    print(f"  {t.title}")
    if t.note:
        print(f"  note: {t.note}")
    return 0


def _set(args, status: str) -> int:
    lines, tasks = load()
    t = find(tasks, args.task_id)
    note = " ".join(args.note).strip()
    if status == "done" and not note and not t.note:
        raise SystemExit(
            "a task is not done without evidence -- pass a note saying how it "
            "was verified, e.g. tasks.py done T-042 \"harness 84/84\"")
    was = t.status
    t.status = status
    if note:
        t.note = f"{note} ({_today()})"
    save(lines, t)
    print(f"{t.task_id}  {was} -> {status}")
    print(f"  {t.title}")
    if t.note:
        print(f"  note: {t.note}")
    return 0


def _branch_block() -> list[int] | None:
    """This branch's task-number block, when it has a status file."""
    try:
        import agents
        s = agents.local_status(agents.current_branch())
    except Exception:
        return None
    block = ((s or {}).get("ids") or {}).get("T")
    return list(block) if block and len(block) == 2 else None


def cmd_add(args) -> int:
    lines, tasks = load()
    numbers = [int(t.task_id.split("-")[1]) for t in tasks]
    # New work is numbered in its area's band so the registry stays readable:
    # 100s render, 200s ui, 300s feature, 400s map, 500s review, 600s
    # integrity, 700s test, 800s meta.
    band = {"render": 100, "ui": 200, "feature": 300, "map": 400,
            "review": 500, "integrity": 600, "test": 700, "meta": 800}.get(args.area, 900)
    in_band = [n for n in numbers if band <= n < band + 100]
    number = (max(in_band) + 1) if in_band else band
    # A full band (the 900s reached 999) must not hand out the same overflow
    # number forever: past the band, continue after the highest id in use,
    # and never reuse an id that exists.
    if number >= band + 100:
        number = max(numbers) + 1
    # A session that shares the repository with others numbers from its own
    # block (engine/agents.py), so two sessions never hand out the same id.
    block = _branch_block()
    if block:
        free = [n for n in range(block[0], block[1] + 1) if n not in numbers]
        if not free:
            raise SystemExit(f"This branch's block T-{block[0]}..T-{block[1]} is full: "
                             "take a new one with `python engine/agents.py init`.")
        number = free[0]
    while number in numbers:
        number += 1
    task = Task(f"T-{number:03d}", "open", args.area, args.title,
                " ".join(args.note).strip())

    # Insert after the last row of the same band, or at the end of the table.
    last = None
    for i, line in enumerate(lines):
        m = ROW.match(line.strip())
        if m and m.group(2) in STATUSES:
            n = int(m.group(1).split("-")[1])
            if band <= n < band + 100 or last is None:
                last = i
    lines.insert(last + 1, task.row())
    REGISTRY.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"added {task.task_id}  [{task.area}]  {task.title}")
    return 0


def cmd_ask(args) -> int:
    """Record a question for the user so it is not lost between sessions."""
    lines, _tasks = load()
    question = " ".join(args.question).strip()
    nums = [int(m.group(1)) for line in lines
            if (m := re.match(r"^\|\s*Q-(\d+)\s*\|", line.strip()))]
    row = f"| Q-{max(nums, default=0) + 1} | {question} | asked {_today()} |"
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip().startswith("| Q-"):
            lines.insert(i + 1, row)
            break
    else:
        lines.append("")
        lines.append("| # | Question | Why it matters |")
        lines.append("|---|---|---|")
        lines.append(row)
    REGISTRY.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"recorded: {row}")
    return 0


def summary(tasks: list[Task]) -> None:
    counts = {s: sum(1 for t in tasks if t.status == s) for s in STATUSES}
    total = len(tasks)
    pct = 100 * counts["done"] / total if total else 0
    print(f"  {counts['done']} done · {counts['partial']} partial · "
          f"{counts['open']} open · {counts['blocked']} blocked "
          f"— {pct:.0f}% of {total}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    ls = sub.add_parser("list", help="every task, grouped by area")
    ls.add_argument("--status", choices=STATUSES)
    ls.add_argument("--area")
    ls.set_defaults(fn=cmd_list)

    nx = sub.add_parser("next", help="what to pick up now")
    nx.add_argument("-n", "--count", type=int, default=12)
    nx.set_defaults(fn=cmd_next)

    sh = sub.add_parser("show", help="one task in full")
    sh.add_argument("task_id")
    sh.set_defaults(fn=cmd_show)

    for name, status in (("start", "partial"), ("done", "done"),
                         ("block", "blocked"), ("open", "open")):
        c = sub.add_parser(name, help=f"mark a task {status}")
        c.add_argument("task_id")
        c.add_argument("note", nargs="*")
        c.set_defaults(fn=lambda a, s=status: _set(a, s))

    ad = sub.add_parser("add", help="record a new instruction from the user")
    ad.add_argument("title")
    ad.add_argument("--area", default="feature")
    ad.add_argument("--note", nargs="*", default=[])
    ad.set_defaults(fn=cmd_add)

    qa = sub.add_parser("ask", help="record a question for the user")
    qa.add_argument("question", nargs="+")
    qa.set_defaults(fn=cmd_ask)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
