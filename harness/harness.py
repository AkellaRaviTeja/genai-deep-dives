"""A minimal coding-agent harness, with every part switchable, for measuring
what the harness (not the model) does to results.

    uv run python harness/harness.py check                     prove the tasks are sound
    uv run python harness/harness.py run MODEL VARIANT [TASK]  run and grade
    uv run python harness/harness.py grid                      the full experiment

The loop is the same for every variant. A variant only switches parts on or off:

    oneshot      no loop: all the code in one prompt, one answer, applied as is
    loop         tools to list, read and edit files; no way to run anything
    tests        + a run_tests tool
    agents       + AGENTS.md in the system prompt (the instructions file)
    hook         + after every edit, the harness runs the tests itself and appends the result
    toolbloat    'agents' + 40 irrelevant tool definitions
    preload      'agents' + every file pasted into the first message
"""

import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import pathlib
import datetime

ROOT = pathlib.Path(__file__).resolve().parent
BASE = ROOT / "base"
OUT = ROOT.parent / "results" / "harness"
RUNS = pathlib.Path(os.environ.get("HARNESS_RUNS", ROOT / "runs"))
sys.path.insert(0, str(ROOT))
from tasks import TASKS, STUB  # noqa: E402

MAX_TURNS = 16
MAX_NEW = 1200
OUTPUT_CAP = 2500
PROMPT_LIMIT = 6500

VARIANTS = {
    "oneshot": dict(loop=False),
    "loop": dict(loop=True, tests=False, agents=False, hook=False),
    "tests": dict(loop=True, tests=True, agents=False, hook=False),
    "agents": dict(loop=True, tests=True, agents=True, hook=False),
    "hook": dict(loop=True, tests=True, agents=True, hook=True),
    "toolbloat": dict(loop=True, tests=True, agents=True, hook=False, bloat=True),
    "preload": dict(loop=True, tests=True, agents=True, hook=False, preload=True),
}


# ---- workspaces --------------------------------------------------------------------------------
def stub_function(path, name):
    src = path.read_text()
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            body = node.body
            first = (
                body[1]
                if (
                    isinstance(body[0], ast.Expr)
                    and isinstance(getattr(body[0], "value", None), ast.Constant)
                    and len(body) > 1
                )
                else body[0]
            )
            indent = " " * first.col_offset
            start, end = first.lineno - 1, node.end_lineno
            new = lines[:start] + [indent + STUB.lstrip()] + lines[end:]
            path.write_text("".join(new))
            return
    raise SystemExit(f"no function {name} in {path}")


def make_workspace(task, keep_agents):
    ws = pathlib.Path(tempfile.mkdtemp(prefix=f"h-{task['id']}-"))
    shutil.copytree(
        BASE, ws, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".*", "__pycache__")
    )
    if task.get("stub"):
        stub_function(ws / task["stub"][0], task["stub"][1])
    if task.get("bug"):
        f, old, new = task["bug"]
        p = ws / f
        s = p.read_text()
        assert old in s, (task["id"], old)
        p.write_text(s.replace(old, new, 1))
    if not keep_agents:
        (ws / "AGENTS.md").unlink()
    for junk in ws.rglob("__pycache__"):
        shutil.rmtree(junk, ignore_errors=True)
    return ws


def pytest(dirpath, target, timeout=60):
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", target],
            cwd=dirpath,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        return r.returncode, (r.stdout + r.stderr)
    except subprocess.TimeoutExpired:
        return 124, "tests timed out"


def grade(ws, task):
    """Pristine original tests + the hidden test, against the agent's package."""
    g = pathlib.Path(tempfile.mkdtemp(prefix="grade-"))
    shutil.copytree(ws / "invoicing", g / "invoicing")
    shutil.copytree(BASE / "tests", g / "tests")
    (g / "tests" / "test_hidden.py").write_text(task["hidden"])
    code, out = pytest(g, "tests")
    shutil.rmtree(g, ignore_errors=True)
    return code == 0, out[-1500:]


def tests_touched(ws):
    return sorted(
        p.name
        for p in (ws / "tests").glob("*.py")
        if not (BASE / "tests" / p.name).exists()
        or (BASE / "tests" / p.name).read_text() != p.read_text()
    )


def source_files(ws):
    return sorted(
        str(p.relative_to(ws))
        for p in ws.rglob("*")
        if p.is_file()
        and "__pycache__" not in p.parts
        and not any(x.startswith(".") for x in p.relative_to(ws).parts)
    )


# ---- the model -----------------------------------------------------------------------------------
class Model:
    def __init__(self, name):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.torch = torch
        self.name = name
        self.tok = AutoTokenizer.from_pretrained(name)
        self.m = (
            AutoModelForCausalLM.from_pretrained(name, dtype=torch.bfloat16)
            .to("cuda")
            .eval()
        )

    def count(self, messages, tools=None):
        text = self.tok.apply_chat_template(
            messages, tools=tools, tokenize=False, add_generation_prompt=True
        )
        return len(self.tok(text).input_ids)

    def chat(self, messages, tools=None):
        text = self.tok.apply_chat_template(
            messages, tools=tools, tokenize=False, add_generation_prompt=True
        )
        ids = self.tok(text, return_tensors="pt").input_ids.to("cuda")
        try:
            with self.torch.no_grad():
                out = self.m.generate(
                    ids,
                    max_new_tokens=MAX_NEW,
                    do_sample=False,
                    pad_token_id=self.tok.eos_token_id,
                )
        except self.torch.OutOfMemoryError:
            self.torch.cuda.empty_cache()
            return "[the harness ran out of GPU memory for this turn]", ids.shape[1], 0
        new = out[0, ids.shape[1] :]
        return (
            self.tok.decode(new, skip_special_tokens=False)
            .replace("<|im_end|>", "")
            .replace("<|endoftext|>", "")
            .strip(),
            ids.shape[1],
            len(new),
        )


# ---- tools ---------------------------------------------------------------------------------------
TOOLS = {
    "list_files": ("List every file in the repository.", {}),
    "read_file": (
        "Read one file. Always read a file before you change it.",
        {"path": "relative path"},
    ),
    "write_file": (
        "Replace a file's entire content, or create a new file.",
        {"path": "relative path", "content": "the full new file"},
    ),
    "replace": (
        "Replace one exact snippet in a file with new text. The snippet must appear exactly once.",
        {
            "path": "relative path",
            "old": "exact existing text",
            "new": "replacement text",
        },
    ),
    "run_tests": ("Run the test suite with pytest and see the result.", {}),
    "done": (
        "Finish. Say what you changed and whether the tests pass.",
        {"summary": "one or two sentences"},
    ),
}
BLOAT = [
    "jira_create_issue",
    "jira_search",
    "slack_post_message",
    "slack_read_channel",
    "github_create_pr",
    "github_list_issues",
    "s3_upload",
    "s3_download",
    "sql_query_readonly",
    "sql_explain",
    "send_email",
    "calendar_create_event",
    "docker_build",
    "docker_run",
    "k8s_get_pods",
    "k8s_logs",
    "grafana_query",
    "sentry_list_errors",
    "figma_get_frame",
    "notion_search",
    "confluence_search",
    "pagerduty_ack",
    "stripe_refund",
    "stripe_list_charges",
    "translate_text",
    "web_search",
    "web_fetch",
    "image_generate",
    "pdf_extract",
    "spreadsheet_read",
    "spreadsheet_write",
    "http_request",
    "redis_get",
    "redis_set",
    "vault_read_secret",
    "terraform_plan",
    "terraform_apply",
    "npm_install",
    "pip_install",
    "cron_schedule",
]


def tool_schemas(v):
    """The tools as JSON schemas, passed through the model's own chat template."""

    def fn(name, desc, props, required):
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": desc,
                "parameters": {
                    "type": "object",
                    "properties": {
                        k: {"type": "string", "description": d}
                        for k, d in props.items()
                    },
                    "required": required,
                },
            },
        }

    names = [n for n in TOOLS if v.get("tests") or n != "run_tests"]
    out = [fn(n, TOOLS[n][0], TOOLS[n][1], list(TOOLS[n][1])) for n in names]
    if v.get("bloat"):
        out += [
            fn(
                n,
                f"{n.replace('_', ' ').capitalize()} in the team's workspace.",
                {"input": "what to do"},
                ["input"],
            )
            for n in BLOAT
        ]
    return out


def system_prompt(v, ws):
    s = (
        "You are a coding agent working in a small Python repository (package `invoicing`, tests in `tests/`). "
        "Use the tools to inspect and change the code. Make one tool call at a time and wait for its result. "
        "Change files only with write_file or replace; code you write in a message is not applied. "
        "When the task is complete, call done."
    )
    if v.get("agents"):
        s += (
            "\n\nThe repository's instructions file, AGENTS.md:\n\n"
            + (ws / "AGENTS.md").read_text()
        )
    return s


def parse_calls(text):
    """Qwen's native <tool_call>{"name": ..., "arguments": {...}}</tool_call>, or the same
    JSON without the tags, which small models often drop after the first turn."""
    dec = json.JSONDecoder()
    found = re.findall(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", text, re.S)
    candidates = [c for c in found]
    i = text.find("{")
    while i != -1 and len(candidates) < 8:
        try:
            obj, end = dec.raw_decode(text, i)
            candidates.append(obj)
            i = text.find("{", end)
        except json.JSONDecodeError:
            i = text.find("{", i + 1)
    for c in candidates:
        if isinstance(c, str):
            try:
                c = json.loads(c)
            except json.JSONDecodeError:
                continue
        if isinstance(c, dict) and isinstance(c.get("name"), str):
            args = c.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            if isinstance(args, dict):
                return [{"tool": c["name"], **args}]
    return []


def compact(msgs, model, tools, limit):
    """Keep the prompt under `limit` tokens: shorten the oldest tool results first."""
    for m in msgs[2:-2]:
        if model.count(msgs, tools) <= limit:
            return
        if m["role"] == "tool" and len(m["content"]) > 300:
            m["content"] = (
                m["content"][:300] + "\n[older result shortened by the harness]"
            )


def run_tool(call, ws, v):
    name = call.get("tool")
    try:
        if name == "list_files":
            return "\n".join(source_files(ws))
        if name in ("read_file", "write_file", "replace"):
            p = (ws / call["path"]).resolve()
            if not str(p).startswith(str(ws.resolve())):
                return f"error: {call['path']} is outside the repository. Paths are relative to the repository root, for example invoicing/tax.py"
            if name == "read_file":
                return (
                    p.read_text()
                    if p.exists()
                    else f"error: {call['path']} does not exist"
                )
            if name == "write_file":
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(call["content"])
                return (
                    f"wrote {call['path']} ({len(call['content'].splitlines())} lines)"
                )
            s = p.read_text() if p.exists() else ""
            n = s.count(call["old"])
            if n != 1:
                return f"error: the old text appears {n} times in {call['path']}; it must appear exactly once"
            p.write_text(s.replace(call["old"], call["new"], 1))
            return f"replaced 1 snippet in {call['path']}"
        if name == "run_tests" and v.get("tests"):
            code, out = pytest(ws, "tests")
            return ("PASSED" if code == 0 else "FAILED") + "\n" + out[-OUTPUT_CAP:]
        if name == "done":
            return "ok"
        if v.get("bloat") and name in BLOAT:
            return f"error: {name} is not available in this repository"
        return f"error: unknown tool {name!r}"
    except KeyError as e:
        return f"error: missing argument {e}"
    except Exception as e:  # a tool must never crash the harness
        return f"error: {type(e).__name__}: {e}"


# ---- one run ---------------------------------------------------------------------------------------
def oneshot(model, task, ws):
    files = [f for f in source_files(ws) if f.endswith(".py")]
    listing = "\n\n".join(
        f"### {f}\n```python\n{(ws / f).read_text()}```" for f in files
    )
    msgs = [
        {"role": "system", "content": "You are an expert Python developer."},
        {
            "role": "user",
            "content": f"Repository files:\n\n{listing}\n\nTask: {task['prompt']}\n\n"
            "Reply with the complete new content of every file you change, each as:\n"
            "### path/to/file.py\n```python\n...full file...\n```",
        },
    ]
    text, tin, tout = model.chat(msgs)
    for path, body in re.findall(
        r"###\s*(\S+\.py)\s*\n```(?:python)?\n(.*?)```", text, re.S
    ):
        p = (ws / path).resolve()
        if str(p).startswith(str(ws.resolve())):
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body)
    return [{"role": "assistant", "content": text}], dict(
        turns=1,
        tokens_in=tin,
        tokens_out=tout,
        calls={},
        parse_errors=0,
        claimed_done=True,
        prompt_tokens_first=tin,
    )


def agent(model, task, ws, v):
    msgs = [{"role": "system", "content": system_prompt(v, ws)}]
    first = f"Task: {task['prompt']}"
    if v.get("preload"):
        first += "\n\nAll repository files:\n\n" + "\n\n".join(
            f"### {f}\n```\n{(ws / f).read_text()}```" for f in source_files(ws)
        )
    msgs.append({"role": "user", "content": first})
    st = dict(
        turns=0,
        tokens_in=0,
        tokens_out=0,
        calls={},
        parse_errors=0,
        claimed_done=False,
        hook_runs=0,
        prompt_tokens_first=None,
        bloat_calls=0,
        last_tests=None,
    )
    tools = tool_schemas(v)
    for _ in range(MAX_TURNS):
        compact(msgs, model, tools, PROMPT_LIMIT)
        text, tin, tout = model.chat(msgs, tools)
        st["turns"] += 1
        st["tokens_in"] += tin
        st["tokens_out"] += tout
        st["prompt_tokens_first"] = st["prompt_tokens_first"] or tin
        calls = parse_calls(text)
        if not calls:
            st["parse_errors"] += 1
            msgs.append({"role": "assistant", "content": text})
            msgs.append(
                {
                    "role": "user",
                    "content": "No tool call found. Use the tools: call one, in the <tool_call> format.",
                }
            )
            continue
        call = calls[0]
        name = call["tool"]
        msgs.append(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": {
                                k: v2 for k, v2 in call.items() if k != "tool"
                            },
                        },
                    }
                ],
            }
        )
        st["calls"][name] = st["calls"].get(name, 0) + 1
        if name in BLOAT:
            st["bloat_calls"] += 1
        result = run_tool(call, ws, v)
        if name == "run_tests":
            st["last_tests"] = result.startswith("PASSED")
        if (
            v.get("hook")
            and name in ("write_file", "replace")
            and not result.startswith("error")
        ):
            code, out = pytest(ws, "tests")
            st["hook_runs"] += 1
            st["last_tests"] = code == 0
            result += (
                "\n\n[hook: tests ran automatically after your edit]\n"
                + ("PASSED" if code == 0 else "FAILED")
                + "\n"
                + out[-OUTPUT_CAP:]
            )
        if name == "done":
            st["claimed_done"] = True
            break
        msgs.append({"role": "tool", "content": result[: OUTPUT_CAP + 400]})
    return msgs, st


def run_one(model, task, variant):
    v = VARIANTS[variant]
    ws = make_workspace(task, keep_agents=v.get("agents", False))
    t0 = time.time()
    msgs, st = oneshot(model, task, ws) if not v["loop"] else agent(model, task, ws, v)
    passed, gout = grade(ws, task)
    rec = dict(
        task=task["id"],
        kind=task["kind"],
        rules=task["rules"],
        variant=variant,
        model=model.name,
        passed=passed,
        seconds=round(time.time() - t0, 1),
        tests_touched=tests_touched(ws),
        grade_tail=gout[-600:],
        **st,
    )
    RUNS.mkdir(exist_ok=True)
    tag = f"{model.name.split('/')[-1]}__{variant}__{task['id']}"
    (RUNS / f"{tag}.json").write_text(
        json.dumps({**rec, "transcript": msgs}, ensure_ascii=False, indent=1)
    )
    shutil.rmtree(ws, ignore_errors=True)
    return rec


# ---- checks and the grid -------------------------------------------------------------------------------
def check_tasks():
    """Every hidden test must pass on the reference and fail on the starting state."""
    sys.path.insert(0, str(ROOT / "ref"))
    from features import FEATURES

    bad = 0
    for t in TASKS:
        start = make_workspace(t, keep_agents=True)
        ok_start, _ = grade(start, t)
        ref = pathlib.Path(tempfile.mkdtemp(prefix="ref-"))
        shutil.copytree(BASE, ref, dirs_exist_ok=True)
        for f, old, new in FEATURES.get(t["id"], []):
            p = ref / f
            s = p.read_text()
            p.write_text(s + new if old is None else s.replace(old, new, 1))
        ok_ref, out = grade(ref, t)
        flag = "ok" if (ok_ref and not ok_start) else "BAD"
        bad += flag == "BAD"
        print(
            f"  {flag:<3} {t['id']:<22} reference {'passes' if ok_ref else 'FAILS'}, starting state {'passes' if ok_start else 'fails'}"
        )
        if not ok_ref:
            print(out[-800:])
        shutil.rmtree(start, ignore_errors=True)
        shutil.rmtree(ref, ignore_errors=True)
    print(f"{len(TASKS)} tasks checked, {bad} bad")
    if not TASKS or bad:
        raise SystemExit(1)


def run_grid(models, variants, task_ids=None):
    OUT.mkdir(parents=True, exist_ok=True)
    tasks = [t for t in TASKS if not task_ids or t["id"] in task_ids]
    for name in models:
        model = Model(name)
        for variant in variants:
            recs = []
            for t in tasks:
                tag = f"{name.split('/')[-1]}__{variant}__{t['id']}"
                cached = RUNS / f"{tag}.json"
                if cached.exists():
                    r = json.loads(cached.read_text())
                    r.pop("transcript", None)
                else:
                    r = run_one(model, t, variant)
                recs.append(r)
                print(
                    f"  {name.split('/')[-1]:<24} {variant:<9} {t['id']:<22} {'PASS' if r['passed'] else 'fail'}  turns {r['turns']:>2}  in {r['tokens_in']:>6}  {r['seconds']:>5}s",
                    flush=True,
                )
            n = sum(r["passed"] for r in recs)
            print(f"== {name} {variant}: {n}/{len(recs)} passed", flush=True)
        del model
        import torch

        torch.cuda.empty_cache()
    summarise()


def summarise():
    rows = [json.loads(p.read_text()) for p in sorted(RUNS.glob("*.json"))]
    for r in rows:
        r.pop("transcript", None)
    if not rows:
        raise SystemExit("no runs to summarise")
    cells = {}
    for r in rows:
        k = (r["model"], r["variant"])
        c = cells.setdefault(
            k,
            dict(
                model=r["model"],
                variant=r["variant"],
                n=0,
                passed=0,
                tokens_in=0,
                tokens_out=0,
                turns=0,
                seconds=0,
                claimed_but_failed=0,
                tests_edited=0,
                parse_errors=0,
                bloat_calls=0,
                rules_n=0,
                rules_passed=0,
            ),
        )
        c["n"] += 1
        c["passed"] += r["passed"]
        c["tokens_in"] += r["tokens_in"]
        c["tokens_out"] += r["tokens_out"]
        c["turns"] += r["turns"]
        c["seconds"] += r["seconds"]
        c["parse_errors"] += r.get("parse_errors", 0)
        c["bloat_calls"] += r.get("bloat_calls", 0)
        c["claimed_but_failed"] += bool(r.get("claimed_done") and not r["passed"])
        c["tests_edited"] += bool(r["tests_touched"])
        if r["rules"]:
            c["rules_n"] += 1
            c["rules_passed"] += r["passed"]
    out = {
        "meta": {
            "tasks": len(TASKS),
            "max_turns": MAX_TURNS,
            "decoding": "greedy",
            "run_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "gpu": "NVIDIA GeForce RTX 5050 Laptop GPU",
        },
        "cells": list(cells.values()),
        "runs": rows,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "harness_grid.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1)
    )
    print(f"\n{len(rows)} runs in {len(cells)} cells -> {OUT / 'harness_grid.json'}")
    for c in cells.values():
        print(
            f"  {c['model'].split('/')[-1]:<24} {c['variant']:<9} {c['passed']:>2}/{c['n']}  rule tasks {c['rules_passed']}/{c['rules_n']}  "
            f"claimed-but-failed {c['claimed_but_failed']}  tests edited {c['tests_edited']}  tokens in {c['tokens_in']}"
        )


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "check":
        check_tasks()
    elif cmd == "run":
        run_grid([sys.argv[2]], [sys.argv[3]], sys.argv[4:] or None)
    elif cmd == "grid":
        # a small local model as the floor: no harness at all, and the fullest harness
        run_grid(["Qwen/Qwen2.5-Coder-3B-Instruct"], ["oneshot", "hook"])
    elif cmd == "summary":
        summarise()
