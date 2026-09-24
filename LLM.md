# Reproduce every number in "What an LLM Actually Does"

Every figure in the episode comes from `llm_experiments.py`, run on
**Qwen2.5-1.5B** (the base model) in bfloat16 on an 8 GB laptop GPU
(NVIDIA RTX 5050). Nothing on screen is invented or illustrative unless the
screen says so.

## Run it

```bash
uv sync --python 3.12          # torch, transformers, tiktoken, accelerate
uv run python llm_experiments.py            # every experiment
uv run python llm_experiments.py truth      # or one of them
uv run python llm_experiments.py truth loop # or several
```

A CUDA GPU is optional; on a CPU the experiments still run, just slower.
The model (about 3 GB) and the tokenizer files download on first run.
`corpus/TruthfulQA.csv` is checked in next to the UDHR texts; `corpus/cities.csv` has no
licence upstream, so `uv run python fetch_data.py` downloads it from its source first. Results are written as JSON, and each file records the model, library
versions, device and time of the run.

## The experiments

| Name | What it measures | Shown in |
|---|---|---|
| `tokenizers` | The same text through 7 tokenizers: token IDs, "strawberry", digits, and the Universal Declaration of Human Rights in English, Telugu and Hindi | The tokenizer |
| `distribution` | The next-token distribution after "The invoice total is": all 151,936 logits, the top 12, entropy, and the effect of temperature | One step |
| `samplers` | The same settings through two sampler orders (Transformers: temperature first; llama.cpp: temperature last), plus a 15-setting sweep | One step |
| `samples` | 200 samples: how often each first token came out, against the share softmax predicted | One step |
| `loop` | Greedy generation one step at a time, and where the end token stood at each step | The loop |
| `context` | The next token in a Go handler: without the interface, with it, and with the method renamed | The failure |
| `kvcache` | Speed with and without the KV cache at 32 to 1,024 tokens, its memory per token, and the card's measured bandwidth | The loop |
| `surprise` | Per-token loss on one line of an invoice email | Where the scores come from |
| `truth` | 748 true/false city pairs (Geometry of Truth) and 790 TruthfulQA questions, scored on the tokens that differ | How it goes wrong |
| `arithmetic` | 200 random 3-digit x 2-digit problems: exact and per-digit accuracy, base model greedy, then the instruct model answering directly and writing its working | How it goes wrong |
| `determinism` | One prompt copied into batches of 1 to 64 identical rows, 512 greedy tokens: score drift and where the text splits | How it goes wrong |
| `chat_template` | What the instruct model receives for a two-message chat | What to do |

## Caveats worth knowing

- One small base model. Chat models, bigger models and other families will
  give different numbers; the mechanisms are the same.
- The Telugu and Hindi figures use one parallel document (the UDHR, from the
  Unicode Consortium's `unicode-org/udhr` repository). Other corpora give
  somewhat different ratios; Petrov et al. (NeurIPS 2023) report 8.34x for
  Telugu under GPT-4's tokenizer on FLORES-200.
- The sampler-order experiment applies each engine's documented order to the
  same logits. The Transformers side is asserted equal to Transformers' own
  logits processors; the llama.cpp side is not a run of llama.cpp. Settings
  were chosen so no token sits within 8% of a cutoff (at min_p 0.05 one token
  clears it by 0.01%, which bf16 rounding could flip).
- The final layer is recomputed in float32 for every distribution shown; the
  network itself runs in bfloat16.
- `arithmetic` loads the 1.5B instruct model as well (another 3 GB download),
  and parks the base model on the CPU while it runs.
- `determinism` results depend on the GPU and its kernels. On another card the
  split points will differ; the fact that batch size alone moves them will not.
- Timing depends on the GPU. The ratio between cache on and off is the point.
