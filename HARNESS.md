# Reproduce every number in "Harness Engineering, Measured"

Everything here runs on one laptop: an RTX 5050 (8 GB), Go 1.25, Docker, and the
`claude` CLI logged in to a subscription. Nothing uses an API key.

## The codebase and the tasks

`base/` is a small, correct invoicing package (money in integer paise, GST, discounts,
a store, a service layer with permission checks, API handlers) with 10 tests and an
`AGENTS.md` of project rules.

`tasks.py` cuts 24 tasks from it: 8 stubbed functions to implement, 8 planted bugs to fix
and 8 features to add. Each is graded by a hidden test the agent never sees, plus the
original test suite, both run from a pristine copy, so editing the tests cannot help.
`rules` on a task lists the AGENTS.md rules its hidden test checks that the prompt does
not state.

```bash
uv run python harness/harness.py check    # every hidden test passes on a reference, fails on the start
```

## The experiments

| Script | What it measures |
|---|---|
| `claude_grid.py run 3` | The 24 tasks through Claude Code on Haiku, 3 runs each, in 5 harnesses: model only (no tools), edit tools only, + running tests, + CLAUDE.md, + a PostToolUse hook that runs the tests after every edit |
| `impossible.py 3` | 6 tasks whose request contradicts a visible test, in 4 harnesses: tests writable, "never edit tests" in CLAUDE.md, test edits denied by permissions, and an explicit way out. Each run is classified from what changed on disk |
| `claude_overhead.py` | Tokens Claude Code sends for a one-word reply, with and without tools, CLAUDE.md lines and MCP tools |
| `harness.py grid` | A local model (Qwen2.5-Coder-3B-Instruct) in no harness and in the fullest harness of our own minimal agent loop |
| `traps.py` | `go test` on a package with no test files, and Postgres inserts during `CREATE INDEX` with and without `CONCURRENTLY` on 30 million rows |

Every script writes JSON to `results/harness/` and keeps per-run records
(transcripts included for the local model) so any single result can be inspected.

## Caveats

- One model per arm (Haiku for Claude Code, a 3B model locally), one small Python codebase.
  Bigger models and real repositories will give different numbers.
- The benchmark sits near its ceiling: most tasks pass in every harness, so it cannot detect
  gains from tools on this codebase. Read the results per task (`claude_grid.json` has every
  run), not as a single percentage. Three repeats of one task are not independent samples.
- The rules gain comes from three tasks whose hidden test checks a rule that exists only in
  AGENTS.md. That shows the file delivering a fact the code lacks; it is not evidence that
  rules files help in general. `model_only_rules` separates the file from the agent loop.
- The CLAUDE.md used is AGENTS.md verbatim, written for the local harness: it mentions a
  `run_tests` tool that Claude Code does not have, and says not to edit tests.
- "Model only" is not "no harness": it is Claude Code with tools off, every file pasted in,
  and whole files parsed back out. That is close to ideal for a 9k-token repository.
- Claims of passing tests are detected per sentence, skipping headings and hedged sentences;
  the matches for the no-tools harness were checked by hand.
- Impossible tasks are classified from what changed on disk and which commands ran (the
  run is recorded with `--output-format stream-json`); whether the reply flagged the conflict
  is judged by a separate Haiku call. Rewriting a genuinely wrong test to match the request
  is counted separately from weakening a test, and only the latter counts as cheating.
- `claude_overhead.py` measures deltas reliably; its absolute numbers depend on the Claude
  Code version, recorded in the JSON. CLAUDE.md tokens are mostly cache reads.
- The local model ran greedy, once per task, in our own loop; a loop designed for small
  models might do better.
- The Postgres run uses a laptop container; production tables are bigger and busier.
