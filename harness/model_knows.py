"""Does the model know the two facts from the opening? Ask it, cold, with no tools.

uv run python harness/model_knows.py
"""

import datetime
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from claude_grid import claude  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parents[1] / "results" / "harness"
QUESTIONS = {
    "go": "In Go, what does `go test ./internal/api` print, and what exit code does it return, when that package has no _test.go files? Answer in two sentences.",
    "postgres": "In PostgreSQL, does a plain CREATE INDEX on a large table block concurrent INSERTs while it builds? What should a migration use instead? Answer in two sentences.",
}


def main():
    rows = {}
    for key, q in QUESTIONS.items():
        j = claude(["--tools", ""], tempfile.mkdtemp(prefix="ask-"), q)
        rows[key] = {"question": q, "answer": (j.get("result") or "").strip()}
        print(f"  {key}: {rows[key]['answer'][:200]}")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "model_knows.json").write_text(
        json.dumps(
            {
                "model": "haiku",
                "run_at": datetime.datetime.now().isoformat(timespec="seconds"),
                "answers": rows,
            },
            indent=1,
        )
    )
    if len(rows) != len(QUESTIONS) or not all(r["answer"] for r in rows.values()):
        raise SystemExit("missing answers")


if __name__ == "__main__":
    main()
