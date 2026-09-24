# GenAI deep dives: the code and data behind the episodes

Every number in the GenAI deep dives episodes on
[Ravi Teja's YouTube channel](https://www.youtube.com/@RaviTejaAkella) comes from code in
this repository, and every result is checked in, so you can inspect a single run or re-run
the lot.

| Episode | Guide | Code | Results |
|---|---|---|---|
| What an LLM Actually Does, Measured on a Real Model | [LLM.md](LLM.md) | `llm_experiments.py` | `results/llm/` |
| Harness Engineering, Measured: 648 Claude Code Runs | [HARNESS.md](HARNESS.md) | `harness/` | `results/harness/`, plus every run in `harness/claude_runs/`, `harness/impossible_runs/`, `harness/runs/` |

Each `results/*/sources.md` lists the published claims cited on screen, with a link to the
primary source and whether it was verified there.

## Setup

```bash
uv sync --python 3.12          # torch, transformers, tiktoken, pytest, psycopg
uv run python fetch_data.py    # the one dataset that is downloaded, not redistributed
```

A CUDA GPU with 8 GB is enough for everything local; the models download on first use.
The Claude Code experiments need the `claude` CLI, logged in. The Postgres experiment
needs Docker.

## Reproduce

```bash
uv run python llm_experiments.py                  # every LLM experiment
uv run python harness/harness.py check            # the 24 coding tasks are sound
uv run python harness/claude_grid.py run 3        # 24 tasks x 5 harnesses x 3 runs
uv run python harness/impossible.py 3             # 6 impossible tasks x 4 harnesses x 3 runs
uv run python harness/claude_overhead.py          # what Claude Code sends per request
uv run python harness/traps.py                    # the Go and Postgres traps
```

Runs are cached per task, so an interrupted grid resumes where it stopped. Delete a run's
JSON file to redo it. Results will differ in detail from ours: models, CLI versions and
GPUs change. The caveats in each guide say which differences to expect.

## Data

- `corpus/udhr_*`: the Universal Declaration of Human Rights in English, Telugu and Hindi,
  from the Unicode Consortium's [udhr](https://github.com/unicode-org/udhr) collection.
- `corpus/TruthfulQA.csv`: [TruthfulQA](https://github.com/sylinrl/TruthfulQA)
  (Lin, Hilton and Evans, 2022), Apache License 2.0.
- `corpus/cities.csv`: the Geometry of Truth cities set
  ([Marks and Tegmark, 2023](https://github.com/saprmarks/geometry-of-truth)), downloaded by
  `fetch_data.py` at a pinned commit because it carries no licence upstream.

## Licence

The code is MIT licensed (see [LICENSE](LICENSE)). The datasets keep their own terms.
