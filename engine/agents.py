"""How parallel AI sessions on this repository find each other, split the work
and talk -- without being able to message each other directly.

Several sessions (different accounts, devices, products) can work here at
once, each on its own branch.  All of them read the repository, so that is the
channel.  Each session keeps ONE status file of its own,
``_work/agents/<branch>.json`` -- what it is doing, the tasks it has claimed,
the T-/E- number block it numbers new tasks and catalogue entries from, its
messages -- and never writes another session's file, so merging branches never
conflicts over them.  This tool reads every branch's files straight from git
(no merge needed) and says what matters before anything collides:

    python engine/agents.py                 sync: fetch, then the whole picture
    python engine/agents.py init --focus "what I am doing" [--production]
    python engine/agents.py claim T-510 T-909      (refused if another branch has it)
    python engine/agents.py release T-909
    python engine/agents.py post --to <branch|all> "message"
    python engine/agents.py ack <message-id> "done: ... / declined: why"
    python engine/agents.py next            what this session should pick up
    python engine/agents.py id T            next free number in this branch's block (also E)

``--push`` on any writing command commits the status file and pushes it, so
the others see it at their next sync.  A session-start hook runs the sync for
every Claude session (``.claude/settings.json``); other agents are pointed here
by ``AGENTS.md``.

What the sync reports:
  * live branches, the last commit, who holds production, each one's focus;
  * messages addressed to this branch (or "all") it has not answered;
  * a task claimed by two branches;
  * a T-/E- number used for two different things on two branches (the
    collision this tool exists for: T-125 and E-163 on 2026-10-10);
  * files changed on this branch and on another since they diverged --
    where a merge will need care;
  * branches with no status file (their last HANDOFF heading stands in).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIR = "_work/agents"
LIVE_DAYS = 14
T_BLOCK, T_FIRST = 50, 1100          # task blocks: T-1100..T-1149, T-1150..T-1199, ...
E_BLOCK, E_FIRST = 10, 170           # catalogue blocks: E-170..E-179, ...
ROW = re.compile(r"^\|\s*(T-\d+)\s*\|\s*\w+\s*\|\s*[\w-]*\s*\|\s*(.*?)\s*\|")
EHEAD = re.compile(r"^### (E-\d+) -- (.*)$")


# ------------------------------------------------------------------ git
def git(*args: str, check: bool = False) -> str:
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=60)
    if check and out.returncode:
        raise SystemExit(out.stderr.strip() or f"git {' '.join(args)} failed")
    return out.stdout


def current_branch() -> str:
    return git("rev-parse", "--abbrev-ref", "HEAD").strip()


def slug(branch: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", branch).strip("-")


def live_branches(days: int = LIVE_DAYS) -> list[dict]:
    """Remote branches with a commit in the last ``days`` days, newest first."""
    out = git("for-each-ref", "--sort=-committerdate", "refs/remotes/origin",
              "--format=%(refname:short)\t%(committerdate:iso-strict)\t%(subject)")
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = []
    for line in out.splitlines():
        ref, when, subject = (line.split("\t") + ["", ""])[:3]
        if ref in ("origin", "origin/HEAD") or not ref.startswith("origin/"):
            continue
        try:
            at = datetime.fromisoformat(when)
        except ValueError:
            continue
        if at >= since:
            rows.append({"ref": ref, "branch": ref[len("origin/"):], "at": at, "subject": subject})
    return rows


def show(ref: str, path: str) -> str | None:
    out = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=ROOT, capture_output=True,
                         text=True, timeout=60)
    return out.stdout if out.returncode == 0 else None


# ------------------------------------------------------------------ status files
def status_files(ref: str) -> dict[str, dict]:
    """Every status file a branch carries (its own and copies of others')."""
    out = {}
    for name in git("ls-tree", "--name-only", f"{ref}:{DIR}").split():
        if name.endswith(".json"):
            text = show(ref, f"{DIR}/{name}")
            try:
                data = json.loads(text or "")
            except ValueError:
                continue
            if isinstance(data, dict) and data.get("branch"):
                out[data["branch"]] = data
    return out


def gather(branches: list[dict], me: str) -> dict[str, dict]:
    """The newest status of every session, read from every branch (a branch's
    own copy is the authority; a copy carried by another branch fills in when
    the owner's branch is gone or not yet fetched)."""
    seen: dict[str, dict] = {}
    refs = [b["ref"] for b in branches]
    for ref in refs:
        for branch, data in status_files(ref).items():
            own = ref == f"origin/{branch}"
            old = seen.get(branch)
            if old is None or own or (not old.get("_own") and data.get("updated", "") > old.get("updated", "")):
                seen[branch] = {**data, "_own": own}
    mine = local_status(me)
    if mine:
        seen[me] = {**mine, "_own": True}
    return seen


def path_for(branch: str) -> Path:
    return ROOT / DIR / f"{slug(branch)}.json"


def local_status(branch: str) -> dict | None:
    p = path_for(branch)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return None


def write_status(data: dict) -> Path:
    data["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    p = path_for(data["branch"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


# ------------------------------------------------------------------ the checks
def claim_conflicts(statuses: dict[str, dict]) -> dict[str, list[str]]:
    """task id -> the branches that claim it, where more than one does."""
    by: dict[str, list[str]] = {}
    for branch, s in statuses.items():
        for t in s.get("claims", []):
            by.setdefault(t, []).append(branch)
    return {t: sorted(bs) for t, bs in by.items() if len(bs) > 1}


def numbered(text: str, kind: str) -> dict[str, str]:
    """id -> title, from TASKS.md (T) or CATALOG.md (E) text."""
    out = {}
    for line in (text or "").splitlines():
        m = (ROW if kind == "T" else EHEAD).match(line.strip() if kind == "T" else line)
        if m:
            out[m.group(1)] = re.sub(r"\s+", " ", m.group(2)).strip()[:80]
    return out


def id_collisions(texts: dict[str, str], kind: str) -> list[tuple[str, dict[str, str]]]:
    """Ids two branches use for different things: [(id, {branch: title})]."""
    seen: dict[str, dict[str, str]] = {}
    for branch, text in texts.items():
        for i, title in numbered(text, kind).items():
            seen.setdefault(i, {})[branch] = title
    out = []
    for i, titles in sorted(seen.items()):
        distinct = {re.sub(r"\W+", "", t.lower())[:40] for t in titles.values()}
        if len(titles) > 1 and len(distinct) > 1:
            out.append((i, titles))
    return out


def next_block(statuses: dict[str, dict], kind: str) -> list[int]:
    size, first = (T_BLOCK, T_FIRST) if kind == "T" else (E_BLOCK, E_FIRST)
    taken = [tuple(s.get("ids", {}).get(kind) or ()) for s in statuses.values()]
    start = first
    while any(lo <= start + size - 1 and start <= hi for lo, hi in [t for t in taken if len(t) == 2]):
        start += size
    return [start, start + size - 1]


def free_in_block(block: list[int], used: set[int]) -> int | None:
    lo, hi = block
    return next((n for n in range(lo, hi + 1) if n not in used), None)


def unread(statuses: dict[str, dict], me: str) -> list[dict]:
    mine = statuses.get(me) or {}
    answered = set((mine.get("acks") or {}).keys())
    out = []
    for branch, s in statuses.items():
        if branch == me:
            continue
        for m in s.get("messages", []):
            key = f"{branch}:{m.get('id')}"
            # answered by its full key or by its bare id (what `ack <message-id>` suggests)
            if m.get("to") in (me, "all") and key not in answered and m.get("id") not in answered:
                out.append({**m, "from": branch, "key": key})
    return out


BOARD = "_work/AGENTS_BOARD.md"
BOARD_HEAD = re.compile(r"^### (.+?) — from `([^`]+)` to (.+?)(?::|$)")


def board_messages(texts: dict[str, str], me: str, acks: dict) -> list[dict]:
    """Messages left in a branch's markdown board (``_work/AGENTS_BOARD.md``,
    which sessions used before the status files) that name this branch, "both"
    or "all", newest first, minus those this branch has answered."""
    out, seen = [], set()
    short = me.rsplit("/", 1)[-1]
    for branch, text in texts.items():
        lines = (text or "").splitlines()
        for n, line in enumerate(lines):
            m = BOARD_HEAD.match(line)
            if not m or m.group(2) == me:
                continue
            to = m.group(3)
            if not (short in to or re.search(r"\b(both|all|everyone)\b", to)):
                continue
            key = f"board:{m.group(2)}:{m.group(1).strip()}"
            if key in seen or key in acks:
                continue
            seen.add(key)
            body = []
            for nxt in lines[n + 1:]:
                if nxt.startswith("### ") or nxt.startswith("## "):
                    break
                body.append(nxt.strip())
            out.append({"key": key, "from": m.group(2), "at": m.group(1),
                        "text": re.sub(r"\s+", " ", " ".join(body)).strip()[:600]})
    return out


def changed_files(ref: str, base: str) -> set[str]:
    mb = git("merge-base", ref, base).strip()
    return set(git("diff", "--name-only", f"{mb}...{ref}").split()) if mb else set()


# ------------------------------------------------------------------ commands
def _push(paths: list[Path], message: str) -> None:
    git("add", *[str(p.relative_to(ROOT)) for p in paths], check=True)
    if git("diff", "--cached", "--name-only").strip():
        git("commit", "-q", "-m", message, check=True)
    branch = current_branch()
    for _ in range(4):
        if subprocess.run(["git", "push", "-q", "-u", "origin", branch], cwd=ROOT,
                          capture_output=True, timeout=120).returncode == 0:
            print(f"pushed to origin/{branch}")
            return
    print("push failed: commit made locally; push it before you stop", file=sys.stderr)


def cmd_sync(args) -> int:
    if not args.no_fetch:
        git("fetch", "-q", "--all", "--prune")
    me = current_branch()
    branches = live_branches()
    statuses = gather(branches, me)
    brief = args.brief
    print(f"This session: {me}" + ("" if me in statuses else "  (no status file: run `python engine/agents.py init --focus ...`)"))
    print("\nLive branches:")
    for b in branches[: (6 if brief else 20)]:
        s = statuses.get(b["branch"]) or {}
        tag = " [production]" if s.get("holds_production") else ""
        focus = s.get("focus") or (("(no status file) " if b["branch"] != "main" else "last handoff: ")
                                   + (last_handoff(b["ref"]) or b["subject"]))
        print(f"  {b['at']:%m-%d %H:%M}  {b['branch']}{tag}\n      {focus[:110]}")
    msgs = unread(statuses, me)
    boards = {b["branch"]: show(b["ref"], BOARD) or "" for b in branches if b["branch"] != me}
    msgs += board_messages(boards, me, (statuses.get(me) or {}).get("acks") or {})
    print(f"\nMessages for you: {len(msgs)}  (answer one: python engine/agents.py ack <key> \"...\")")
    for m in msgs:
        print(f"  [{m['key']}] {m.get('at', '')[:16]} from {m['from']}:\n      {m.get('text', '')}")
    clash = claim_conflicts(statuses)
    if clash:
        print("\nClaimed by more than one branch:")
        for t, bs in clash.items():
            print(f"  {t}: {', '.join(bs)}")
    refs = {b["branch"]: b["ref"] for b in branches}
    for kind, path in (("T", "TASKS.md"), ("E", "knowledge/errors/CATALOG.md")):
        texts = {br: show(ref, path) or "" for br, ref in refs.items()}
        local = ROOT / path
        if local.exists():
            texts[me] = local.read_text(encoding="utf-8")
        cols = id_collisions(texts, kind)
        if cols:
            print(f"\n{kind}- numbers used for different things:")
            for i, titles in cols[:12]:
                print(f"  {i}: " + " | ".join(f"{b}: {t}" for b, t in titles.items()))
    if not brief and git("rev-parse", "--verify", "-q", "origin/main").strip():
        mine = changed_files("HEAD", "origin/main")
        for b in branches:
            if b["branch"] in (me, "main"):
                continue
            both = mine & changed_files(b["ref"], "origin/main")
            if both:
                print(f"\nFiles changed here and on {b['branch']} ({len(both)}): "
                      + ", ".join(sorted(both)[:8]) + (" ..." if len(both) > 8 else ""))
    if me not in statuses:
        print("\nNo status file for this branch yet -- `init` it so the others see what you take.")
    return 0


def last_handoff(ref: str) -> str:
    text = show(ref, "_work/HANDOFF.md") or ""
    heads = [l[3:].strip() for l in text.splitlines() if l.startswith("## ")]
    return heads[-1] if heads else ""


def _mine(args, create: bool = False) -> dict:
    me = current_branch()
    s = local_status(me)
    if s is None:
        if not create:
            raise SystemExit("No status file for this branch: run `python engine/agents.py init --focus ...` first.")
        s = {"branch": me, "focus": "", "claims": [], "ids": {}, "messages": [], "acks": {}}
    return s


def cmd_init(args) -> int:
    if not args.no_fetch:
        git("fetch", "-q", "--all", "--prune")
    me = current_branch()
    s = _mine(args, create=True)
    if args.focus:
        s["focus"] = args.focus
    if args.session:
        s["session"] = args.session
    s["holds_production"] = bool(args.production)
    others = {b: v for b, v in gather(live_branches(), me).items() if b != me}
    for kind, given in (("T", args.t_block), ("E", args.e_block)):
        if given:
            lo, hi = (int(x) for x in given.replace("..", "-").split("-"))
            clash = [b for b, v in others.items()
                     if len(v.get("ids", {}).get(kind) or ()) == 2
                     and v["ids"][kind][0] <= hi and lo <= v["ids"][kind][1]]
            if clash:
                raise SystemExit(f"{kind}-{lo}..{hi} overlaps the block of {', '.join(clash)}")
            s.setdefault("ids", {})[kind] = [lo, hi]
        elif not s.get("ids", {}).get(kind):
            s.setdefault("ids", {})[kind] = next_block(others, kind)
    p = write_status(s)
    print(f"{p.relative_to(ROOT)}: blocks T-{s['ids']['T'][0]}..T-{s['ids']['T'][1]}, "
          f"E-{s['ids']['E'][0]}..E-{s['ids']['E'][1]}")
    if args.push:
        _push([p], f"agents: {me} status (focus, number blocks)")
    return 0


def cmd_claim(args, release: bool = False) -> int:
    me = current_branch()
    s = _mine(args)
    if not release and not args.force:
        others = {b: v for b, v in gather(live_branches(), me).items() if b != me}
        taken = {t: b for b, v in others.items() for t in v.get("claims", [])}
        refused = [f"{t} ({taken[t]})" for t in args.tasks if t in taken]
        if refused:
            print("Claimed by another branch, not taken: " + ", ".join(refused)
                  + "\n  ask in a message, or --force if its owner agreed")
            args.tasks = [t for t in args.tasks if t not in taken]
    claims = s.setdefault("claims", [])
    for t in args.tasks:
        if release and t in claims:
            claims.remove(t)
        elif not release and t not in claims:
            claims.append(t)
    p = write_status(s)
    print(f"claims: {', '.join(claims) or '(none)'}")
    if args.push:
        _push([p], f"agents: {me} {'releases' if release else 'claims'} {' '.join(args.tasks)}")
    return 0


def cmd_post(args) -> int:
    me = current_branch()
    s = _mine(args)
    n = 1 + max((int(str(m.get("id", "0")).rsplit("-", 1)[-1]) for m in s.get("messages", [])
                 if str(m.get("id", "")).rsplit("-", 1)[-1].isdigit()), default=0)
    msg = {"id": f"{slug(me.rsplit('/', 1)[-1])}-{n}", "to": args.to,
           "at": datetime.now(timezone.utc).isoformat(timespec="minutes"), "text": " ".join(args.text)}
    s.setdefault("messages", []).append(msg)
    p = write_status(s)
    print(f"posted {msg['id']} to {args.to}")
    if args.push:
        _push([p], f"agents: message from {me} to {args.to}")
    return 0


def cmd_ack(args) -> int:
    me = current_branch()
    s = _mine(args)
    s.setdefault("acks", {})[args.key] = " ".join(args.reply)
    p = write_status(s)
    print(f"answered {args.key}")
    if args.push:
        _push([p], f"agents: {me} answers {args.key}")
    return 0


def cmd_next(args) -> int:
    me = current_branch()
    statuses = gather(live_branches(), me)
    others = {t for b, v in statuses.items() if b != me for t in v.get("claims", [])}
    mine = (statuses.get(me) or {}).get("claims", [])
    sys.path.insert(0, str(ROOT / "engine"))
    import tasks as registry
    _lines, items = registry.load()
    live = {t.task_id: t for t in items if t.status in ("open", "partial", "blocked")}
    print("Yours (claimed):")
    for t in mine:
        if t in live:
            print("  " + live[t].line())
    print("\nUnclaimed by any session (pick from these, then claim):")
    shown = 0
    for t in sorted(live.values(), key=lambda x: (registry.ORDER[x.status], x.task_id)):
        if t.task_id in others or t.task_id in mine or t.status == "blocked":
            continue
        print("  " + t.line())
        shown += 1
        if shown >= args.count:
            break
    return 0


def cmd_id(args) -> int:
    me = current_branch()
    s = _mine(args)
    block = (s.get("ids") or {}).get(args.kind)
    if not block:
        raise SystemExit("This branch has no block for that kind: run init.")
    branches = live_branches()
    used: set[int] = set()
    path = "TASKS.md" if args.kind == "T" else "knowledge/errors/CATALOG.md"
    texts = [show(b["ref"], path) or "" for b in branches] + [(ROOT / path).read_text(encoding="utf-8")]
    for text in texts:
        used |= {int(i.split("-")[1]) for i in numbered(text, args.kind)}
    n = free_in_block(block, used)
    if n is None:
        raise SystemExit(f"Block {block} is full: run init after removing ids.{args.kind} to take a new one.")
    print(f"{args.kind}-{n}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd")
    sy = sub.add_parser("sync", help="fetch, then the whole picture (the default)")
    sy.add_argument("--brief", action="store_true")
    sy.add_argument("--no-fetch", action="store_true")
    it = sub.add_parser("init", help="create or update this branch's status file")
    it.add_argument("--focus", default="")
    it.add_argument("--session", default="")
    it.add_argument("--production", action="store_true", help="this session holds production")
    it.add_argument("--t-block", default="", help="a task-number block already announced, e.g. 1150-1199")
    it.add_argument("--e-block", default="", help="a catalogue-number block already announced, e.g. 300-339")
    it.add_argument("--no-fetch", action="store_true")
    for name in ("claim", "release"):
        c = sub.add_parser(name, help=f"{name} tasks for this branch")
        c.add_argument("tasks", nargs="+")
        c.add_argument("--force", action="store_true")
    po = sub.add_parser("post", help="leave a message")
    po.add_argument("--to", required=True, help="a branch name, or 'all'")
    po.add_argument("text", nargs="+")
    ak = sub.add_parser("ack", help="answer a message (by the key sync shows)")
    ak.add_argument("key")
    ak.add_argument("reply", nargs="+")
    nx = sub.add_parser("next", help="what this session should pick up")
    nx.add_argument("--count", type=int, default=15)
    i = sub.add_parser("id", help="next free T-/E- number in this branch's block")
    i.add_argument("kind", choices=("T", "E"))
    for sp in (it, po, ak) + tuple(sub.choices[n] for n in ("claim", "release")):
        sp.add_argument("--push", action="store_true", help="commit the status file and push it")
    args = p.parse_args(argv)
    if args.cmd in (None, "sync"):
        if args.cmd is None:
            args.brief, args.no_fetch = False, False
        return cmd_sync(args)
    return {"init": cmd_init, "claim": cmd_claim, "release": lambda a: cmd_claim(a, release=True),
            "post": cmd_post, "ack": cmd_ack, "next": cmd_next, "id": cmd_id}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
