"""The same 24 tasks through a real harness: Claude Code, on Haiku, with its parts
switched on and off through its own settings. Graded by the same hidden tests.

    uv run python harness/claude_grid.py smoke            3 tasks x every variant, once
    uv run python harness/claude_grid.py run [REPEATS]    the full grid (default 3 repeats)
    uv run python harness/claude_grid.py summary

Variants (Claude Code 2.1, `--setting-sources project`, no MCP, no skills):
    model_only   no tools at all: every file pasted into the prompt, one reply, applied as is
    no_tests     Read, Edit, Write, Glob, Grep: it can change code but cannot run anything
    tests        + Bash, allowed to run pytest
    rules        + a CLAUDE.md with the project's rules (the same text as AGENTS.md)
    hook         rules + a PostToolUse hook that runs the tests after every edit and,
                 on failure, feeds the output back (exit code 2)

Runs through the logged-in claude CLI (a subscription), never an API key.
"""

import concurrent.futures as cf
import datetime
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from harness import BASE, grade, make_workspace, pytest, source_files, tests_touched  # noqa: E402
from tasks import TASKS  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent
RUNS = pathlib.Path(os.environ.get("CLAUDE_RUNS", ROOT / "claude_runs"))
OUT = ROOT.parent / "results" / "harness"
VENV_BIN = ROOT.parent / ".venv" / "bin"
MODEL = "haiku"
VARIANTS = ["model_only", "no_tests", "tests", "rules", "hook"]
BIG_VARIANTS = ["model_only_big", "model_only_rules_big", "rules_big"]
EXTRA_VARIANTS = ["model_only_rules"]
LEGACY = ROOT / "big" / "legacy"
CLEAN = [
    "--setting-sources",
    "project",
    "--strict-mcp-config",
    "--disable-slash-commands",
    "--no-session-persistence",
]
EDIT_TOOLS = "Read,Edit,Write,Glob,Grep"
PYTEST_ALLOW = [
    "Bash(pytest:*)",
    "Bash(python -m pytest:*)",
    "Bash(python3 -m pytest:*)",
    "Bash(ls:*)",
    "Bash(cat:*)",
]
HOOK = {
    "hooks": {
        "PostToolUse": [
            {
                "matcher": "Edit|Write|MultiEdit",
                "hooks": [
                    {
                        "type": "command",
                        "command": "out=$(python -m pytest -q -p no:cacheprovider tests 2>&1); code=$?; "
                        'if [ $code -ne 0 ]; then echo "[hook] tests failed after your edit:" >&2; echo "$out" | tail -40 >&2; exit 2; fi; exit 0',
                    }
                ],
            }
        ]
    }
}


def prepare(task, variant):
    ws = make_workspace(task, keep_agents=False)
    if variant.endswith("_big"):
        shutil.copytree(LEGACY, ws / "legacy")
        variant = variant[: -len("_big")]
    if variant in ("rules", "hook"):
        (ws / "CLAUDE.md").write_text((BASE / "AGENTS.md").read_text())
    if variant == "hook":
        (ws / ".claude").mkdir()
        (ws / ".claude" / "settings.json").write_text(json.dumps(HOOK))
    return ws


def claude(args, cwd, prompt, timeout=900):
    env = {
        **os.environ,
        "PATH": f"{VENV_BIN}:{os.environ['PATH']}",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    t0 = time.time()
    big = len(prompt) > 60000  # argv has a per-argument limit; long prompts go through stdin
    r = subprocess.run(
        [
            "claude",
            "-p",
            *([] if big else [prompt]),
            "--model",
            MODEL,
            "--output-format",
            "json",
            *CLEAN,
            *args,
        ],
        cwd=cwd,
        input=prompt if big else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    try:
        j = json.loads(r.stdout)
    except json.JSONDecodeError:
        j = {"is_error": True, "result": (r.stdout + r.stderr)[-500:], "usage": {}}
    j["_seconds"] = round(time.time() - t0, 1)
    return j


def run_one(task, variant, rep):
    tag = f"{variant}__{task['id']}__{rep}"
    path = RUNS / f"{tag}.json"
    if path.exists():
        return json.loads(path.read_text())
    ws = prepare(task, variant)
    if variant.endswith("_big"):
        variant = variant[: -len("_big")]
    if variant in ("model_only", "model_only_rules"):
        files = [f for f in source_files(ws) if f.endswith(".py")]
        listing = "\n\n".join(
            f"### {f}\n```python\n{(ws / f).read_text()}```" for f in files
        )
        rules_text = (
            "The repository's rules file, AGENTS.md:\n\n" + (BASE / "AGENTS.md").read_text() + "\n\n"
            if variant == "model_only_rules"
            else ""
        )
        prompt = (
            f"{rules_text}Repository files:\n\n{listing}\n\nTask: {task['prompt']}\n\nReply with the complete new content of every file you "
            "change, each as:\n### path/to/file.py\n```python\n...full file...\n```"
        )
        j = claude(["--tools", ""], ws, prompt)
        for p, body in re.findall(
            r"###\s*(\S+\.py)\s*\n```(?:python)?\n(.*?)```", j.get("result", ""), re.S
        ):
            dest = (ws / p).resolve()
            if str(dest).startswith(str(ws.resolve())):
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(body)
    else:
        tools = EDIT_TOOLS + ("" if variant == "no_tests" else ",Bash")
        allow = EDIT_TOOLS.split(",") + ([] if variant == "no_tests" else PYTEST_ALLOW)
        prompt = (
            f"{task['prompt']}\n\nWhen you are finished, say whether the tests pass."
        )
        j = claude(
            [
                "--tools",
                tools,
                "--allowedTools",
                *allow,
                "--permission-mode",
                "default",
            ],
            ws,
            prompt,
        )
    passed, gout = grade(ws, task)
    vis = pathlib.Path(tempfile.mkdtemp(prefix="vis-"))
    shutil.copytree(ws / "invoicing", vis / "invoicing")
    shutil.copytree(BASE / "tests", vis / "tests")
    visible_passed = pytest(vis, "tests")[0] == 0
    shutil.rmtree(vis, ignore_errors=True)
    u = j.get("usage") or {}
    rec = dict(
        task=task["id"],
        kind=task["kind"],
        rules=task["rules"],
        variant=tag.split("__")[0],
        rep=rep,
        passed=passed,
        error=bool(j.get("is_error")),
        turns=j.get("num_turns"),
        seconds=j["_seconds"],
        cost_usd=j.get("total_cost_usd"),
        input_tokens=(u.get("input_tokens") or 0)
        + (u.get("cache_creation_input_tokens") or 0)
        + (u.get("cache_read_input_tokens") or 0),
        output_tokens=u.get("output_tokens"),
        tests_touched=tests_touched(ws),
        claimed_pass=bool(
            re.search(
                r"\b(all|the)?\s*tests?\s+(now\s+)?pass", j.get("result", ""), re.I
            )
        )
        and not re.search(r"not pass|fail", j.get("result", ""), re.I),
        denials=len(j.get("permission_denials") or []),
        result=j.get("result", ""),
        visible_passed=visible_passed,
        grade_tail=gout[-500:],
    )
    RUNS.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, ensure_ascii=False, indent=1))
    shutil.rmtree(ws, ignore_errors=True)
    return rec


def grid(task_ids, variants, repeats, workers=3):
    jobs = [
        (t, v, r)
        for r in range(repeats)
        for v in variants
        for t in TASKS
        if not task_ids or t["id"] in task_ids
    ]
    print(f"{len(jobs)} runs, {workers} at a time", flush=True)
    done = 0
    with cf.ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(run_one, *j): j for j in jobs}
        for f in cf.as_completed(futs):
            t, v, r = futs[f]
            done += 1
            try:
                rec = f.result()
                print(
                    f"  [{done}/{len(jobs)}] {v:<10} {t['id']:<22} rep {r}  {'PASS' if rec['passed'] else 'fail'}  "
                    f"turns {rec['turns']}  {rec['seconds']}s  {'ERR ' + rec['result'][:80] if rec['error'] else ''}",
                    flush=True,
                )
            except Exception as e:
                print(
                    f"  [{done}/{len(jobs)}] {v} {t['id']} rep {r}: {type(e).__name__}: {e}",
                    flush=True,
                )
    summary()


CLAIM = re.compile(r"\b(all\s+(\d+\s+)?(of the\s+)?tests?|the\s+tests?|tests?)(\s+in the [\w ]+?)?\s+(now\s+)?pass(ed|es)?\b", re.I)
HEDGE = re.compile(r"\b(should|would|will|verify|please run|to confirm|once|if|expected to|make sure)\b", re.I)


def claims_pass(text):
    """True when the reply asserts, without hedging, that the tests pass."""
    for sent in re.split(r"(?<=[.!?])\s+|\n+", text or ""):
        if sent.lstrip().startswith("#") or re.search(r"\bwhy\b", sent, re.I):
            continue
        if CLAIM.search(sent) and not HEDGE.search(sent) and not re.search(r"\b(not|fail|failing)\b", sent, re.I):
            return True
    return False


def summary():
    rows = [json.loads(p.read_text()) for p in sorted(RUNS.glob("*.json"))]
    if not rows:
        raise SystemExit("no runs")
    for r in rows:
        r["claimed_pass"] = claims_pass(r.get("result", ""))
    cells = {}
    for r in rows:
        c = cells.setdefault(
            r["variant"],
            dict(
                variant=r["variant"],
                n=0,
                passed=0,
                errors=0,
                rule_n=0,
                rule_passed=0,
                plain_n=0,
                plain_passed=0,
                input_tokens=0,
                seconds=0,
                turns=0,
                tests_edited=0,
                claimed_but_failed=0,
                claimed=0,
                cost_usd=0.0,
            ),
        )
        c["n"] += 1
        c["passed"] += r["passed"]
        c["errors"] += r["error"]
        c["input_tokens"] += r["input_tokens"]
        c["seconds"] += r["seconds"]
        c["turns"] += r["turns"] or 0
        c["cost_usd"] += r["cost_usd"] or 0
        c["tests_edited"] += bool(r["tests_touched"])
        c["claimed_but_failed"] += bool(r["claimed_pass"] and not r["passed"])
        c["claimed"] += bool(r["claimed_pass"])
        if r["rules"]:
            c["rule_n"] += 1
            c["rule_passed"] += r["passed"]
        else:
            c["plain_n"] += 1
            c["plain_passed"] += r["passed"]
    order = [c for v in VARIANTS + EXTRA_VARIANTS + BIG_VARIANTS for c in [cells.get(v)] if c]
    ver = subprocess.run(
        ["claude", "--version"], capture_output=True, text=True
    ).stdout.strip()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "claude_grid.json").write_text(
        json.dumps(
            {
                "meta": {
                    "claude_code": ver,
                    "model": MODEL,
                    "tasks": len(TASKS),
                    "run_at": datetime.datetime.now().isoformat(timespec="seconds"),
                    "hook": HOOK,
                },
                "cells": order,
                "runs": [
                    {k: v for k, v in r.items() if k not in ("result", "grade_tail")}
                    for r in rows
                ],
            },
            indent=1,
        )
    )
    for c in order:
        print(
            f"  {c['variant']:<10} {c['passed']:>3}/{c['n']:<3} rules {c['rule_passed']}/{c['rule_n']}  plain {c['plain_passed']}/{c['plain_n']}  "
            f"errors {c['errors']}  tests edited {c['tests_edited']}  claimed {c['claimed']}, of which failed {c['claimed_but_failed']}  "
            f"avg {c['input_tokens'] // max(c['n'], 1):,} input tokens, {c['seconds'] / max(c['n'], 1):.0f} s"
        )


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "summary"
    if cmd == "smoke":
        grid(["bug_subtotal", "impl_gst", "feat_gst_split"], VARIANTS, 1)
    elif cmd == "fixes":
        # the critic round: model only + rules, and bug_not_found regraded everywhere
        grid(None, EXTRA_VARIANTS, 3, workers=4)
        grid(["bug_not_found"], VARIANTS, 3, workers=4)
        grid(None, BIG_VARIANTS, 2, workers=4)
    elif cmd == "big":
        grid(None, BIG_VARIANTS, int(sys.argv[2]) if len(sys.argv) > 2 else 2)
    elif cmd == "bigmodel":
        grid(None, ["model_only_big", "model_only_rules_big"], 2)
    elif cmd == "run":
        grid(None, VARIANTS, int(sys.argv[2]) if len(sys.argv) > 2 else 3)
    else:
        summary()
