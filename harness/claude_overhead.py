"""What Claude Code sends before your first word, measured from the CLI's own usage report.

    uv run python harness/claude_overhead.py

Every condition runs `claude -p "Reply with the single word OK."` on Haiku in a fresh
directory, twice, and records input + cache-creation + cache-read tokens. Runs on the
logged-in subscription through the claude CLI; no API key.

Conditions:
    my_setup          everything this machine loads: user settings, plugins, skills, MCP, memory
    clean             project settings only, no MCP servers, no slash commands or skills
    clean_no_tools    clean, and no built-in tools either
    claudemd_N        clean + a CLAUDE.md of N lines in the working directory
    mcp_N             clean + one MCP server that offers N tools
"""

import datetime
import json
import pathlib
import subprocess
import sys
import tempfile

OUT = pathlib.Path(__file__).resolve().parents[1] / "results" / "harness"
PROMPT = "Reply with the single word OK."
CLEAN = [
    "--setting-sources",
    "project",
    "--strict-mcp-config",
    "--disable-slash-commands",
]

MCP_SERVER = r"""
import json, sys
N = int(sys.argv[1])
TOOLS = [{"name": f"ops_tool_{i:03d}", "description": f"Operations helper number {i}: looks up records in the team's internal system {i} and returns them as JSON. Use only when the user asks about system {i}.",
          "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "description": "what to look up"}, "limit": {"type": "integer", "description": "maximum rows"}}, "required": ["query"]}} for i in range(N)]
for line in sys.stdin:
    msg = json.loads(line)
    if "id" not in msg:
        continue
    m = msg.get("method")
    if m == "initialize":
        res = {"protocolVersion": msg["params"].get("protocolVersion", "2025-06-18"), "capabilities": {"tools": {}}, "serverInfo": {"name": "ops", "version": "1"}}
    elif m == "tools/list":
        res = {"tools": TOOLS}
    elif m == "tools/call":
        res = {"content": [{"type": "text", "text": "[]"}]}
    else:
        res = {}
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": res}) + "\n"); sys.stdout.flush()
"""

CLAUDE_LINE = "- Use integer paise for money; tax rounds half to even; api talks only to the service layer; run `make test` before finishing."


def run(args, cwd):
    r = subprocess.run(
        [
            "claude",
            "-p",
            PROMPT,
            "--model",
            "haiku",
            "--output-format",
            "json",
            "--no-session-persistence",
            *args,
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=300,
    )
    j = json.loads(r.stdout)
    u = j["usage"]
    total = (
        u["input_tokens"]
        + u["cache_creation_input_tokens"]
        + u["cache_read_input_tokens"]
    )
    return {
        "total_input": total,
        "input": u["input_tokens"],
        "cache_write": u["cache_creation_input_tokens"],
        "cache_read": u["cache_read_input_tokens"],
        "result": j.get("result", "")[:40],
    }


def condition(name, args=(), lines=0, tools=0):
    d = pathlib.Path(tempfile.mkdtemp(prefix=f"cc-{name}-"))
    extra = list(args)
    if lines:
        (d / "CLAUDE.md").write_text(
            "# Project rules\n\n" + "\n".join(CLAUDE_LINE for _ in range(lines)) + "\n"
        )
    if tools:
        (d / "server.py").write_text(MCP_SERVER)
        cfg = {
            "mcpServers": {
                "ops": {
                    "command": sys.executable,
                    "args": [str(d / "server.py"), str(tools)],
                }
            }
        }
        (d / "mcp.json").write_text(json.dumps(cfg))
        extra += ["--mcp-config", str(d / "mcp.json")]
    runs = [run(extra, d) for _ in range(2)]
    tot = [r["total_input"] for r in runs]
    print(f"  {name:<16} {tot}")
    return {
        "name": name,
        "lines": lines,
        "tools": tools,
        "runs": runs,
        "total_input": min(tot),
    }


def main():
    ver = subprocess.run(
        ["claude", "--version"], capture_output=True, text=True
    ).stdout.strip()
    rows = [
        condition("my_setup"),
        condition("clean", CLEAN),
        condition("clean_no_tools", CLEAN + ["--tools", ""]),
    ]
    rows += [condition(f"claudemd_{n}", CLEAN, lines=n) for n in (50, 200, 800)]
    rows += [condition(f"mcp_{n}", CLEAN, tools=n) for n in (5, 50, 200)]
    by = {r["name"]: r["total_input"] for r in rows}
    per_line = (by["claudemd_800"] - by["claudemd_50"]) / 750
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "claude_overhead.json").write_text(
        json.dumps(
            {
                "claude_code": ver,
                "model": "haiku",
                "prompt": PROMPT,
                "claude_md_line": CLAUDE_LINE,
                "run_at": datetime.datetime.now().isoformat(timespec="seconds"),
                "tokens_per_claude_md_line": round(per_line, 1),
                "conditions": rows,
            },
            indent=1,
        )
    )
    print(f"  {per_line:.1f} tokens per CLAUDE.md line; wrote claude_overhead.json")
    if len(rows) != 9:
        raise SystemExit("expected 9 conditions")


if __name__ == "__main__":
    main()
