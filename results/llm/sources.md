# Research dossier: "What an LLM actually does"

Episode: geek-level explainer of next-token prediction for software developers.
Compiled 24 September 2026. Every source below was opened and read for this dossier unless a claim is marked otherwise.

Status labels:

- **VERIFIED**: the quote or figure was read directly in the primary source.
- **MEASURED**: computed by this research from primary data or primary code (method stated). Re-run on camera before stating it.
- **PARTIAL**: source read through a summarising fetch, so the wording may not be exact. Re-check before quoting.
- **UNVERIFIED**: no primary source confirmed it. Do not state it as fact.

---

## 1. Claims and sources

### Tokenization

**C1. BPE for neural models comes from machine translation, where it was used to handle rare words.** VERIFIED.
Sennrich, Haddow, Birch, "Neural Machine Translation of Rare Words with Subword Units", ACL 2016, arXiv:1508.07909. https://arxiv.org/abs/1508.07909
Quote: "encoding rare and unknown words as sequences of subword units", using "a segmentation based on the byte pair encoding compression algorithm".

**C2. GPT-2 runs BPE on bytes, not on Unicode characters, so it starts from a base alphabet of 256 symbols.** VERIFIED.
Radford et al., "Language Models are Unsupervised Multitask Learners" (GPT-2), 2019, Section 2.2. https://cdn.openai.com/better-language-models/language_models_are_unsupervised_multitask_learners.pdf
Quote: "a byte-level version of BPE only requires a base vocabulary of size 256". Doing it over Unicode code points "would result in a base vocabulary of over 130,000". It also blocks merges across character categories, because otherwise BPE wasted slots on "dog." "dog!" "dog?": "we prevent BPE from merging across character categories for any byte sequence."

**C3. GPT-2's vocabulary has 50,257 entries, and `<|endoftext|>` is ID 50256.** VERIFIED.
GPT-2 paper: "The vocabulary is expanded to 50,257." tiktoken source `tiktoken_ext/openai_public.py`, function `gpt2()`: `"explicit_n_vocab": 50257`, `special_tokens: {ENDOFTEXT: 50256}`. https://github.com/openai/tiktoken/blob/main/tiktoken_ext/openai_public.py

**C4. BPE is lossless, works on any text, and averages about 4 bytes per token.** VERIFIED.
tiktoken README. https://github.com/openai/tiktoken
Quote: "It's reversible and lossless". Also: "On average, in practice, each token corresponds to about 4 bytes."

**C5. Before BPE runs, a regex splits the text into chunks, and no merge crosses a chunk boundary. In cl100k_base and o200k_base, numbers split into runs of at most 3 digits.** VERIFIED.
tiktoken `tiktoken_ext/openai_public.py`: both `pat_str` values contain `\p{N}{1,3}`.

**C6. cl100k_base has 100,256 mergeable tokens plus special tokens up to ID 100276. o200k_base has 199,998 mergeable tokens, with `<|endoftext|>` = 199999 and `<|endofprompt|>` = 200018.** VERIFIED (special IDs from source) and MEASURED (mergeable counts: line counts of the official `.tiktoken` rank files downloaded from openaipublic.blob.core.windows.net).
Source: `openai_public.py`, functions `cl100k_base()` and `o200k_base()`. A comment above the o200k `pat_str` admits: "I think you can allocate tokens more efficiently across languages."

**C7. "strawberry" splits differently depending on a leading space and on the tokenizer.** MEASURED.
Method: tiktoken's rank-merge BPE, reimplemented in about 15 lines of Python, run on the official rank files. Token IDs equal ranks for mergeable tokens.
- cl100k_base: `"strawberry"` → `str | aw | berry` (IDs 496, 675, 15717). `" strawberry"` → one token (73700).
- o200k_base: `"strawberry"` → `st | raw | berry` (302, 1618, 19772). `" strawberry"` → one token (101830).
- Both: `" STRAWBERRY"` → ` STR | AW | B | ERRY` (4 tokens).
Confirm with `tiktoken` itself on camera.

**C8. Llama 3 uses a 128K vocabulary: 100K tokens taken from tiktoken plus 28K added for non-English text. On English, compression went from 3.17 to 3.94 characters per token compared with Llama 2.** VERIFIED.
Llama Team, "The Llama 3 Herd of Models", arXiv:2407.21783. https://arxiv.org/abs/2407.21783
Quote: "Our token vocabulary combines 100K tokens from the tiktoken tokenizer with 28K additional tokens to better support non-English languages."

**C9. Llama 3 8B's config sets `vocab_size` to 128,256, meaning 128,000 BPE tokens plus 256 special tokens. Examples: 128000 `<|begin_of_text|>`, 128001 `<|end_of_text|>`, 128009 `<|eot_id|>`.** VERIFIED from mirror.
`config.json` and `tokenizer_config.json` in unsloth/llama-3-8b(-Instruct) on Hugging Face, an ungated mirror of the gated meta-llama repo. https://huggingface.co/unsloth/llama-3-8b-Instruct

**C10. Qwen2.5 has 151,643 regular tokens and 22 special tokens (IDs 151643 to 151664). Its model config pads the embedding table to 152,064.** VERIFIED.
https://huggingface.co/Qwen/Qwen2.5-7B-Instruct (`tokenizer_config.json`, `config.json`).
Point for the episode: the number of logits per step equals the padded `vocab_size`, not the number of real tokens.

**C11. Gemma 3 uses the Gemini 2.0 tokenizer, a SentencePiece tokenizer with 262k entries.** VERIFIED.
Gemma Team, "Gemma 3 Technical Report", arXiv:2503.19786. https://arxiv.org/abs/2503.19786
Quote: "The resulting vocabulary has 262k entries. This tokenizer is more balanced for non-English languages." The `config.json` value is 262,208 (unsloth/gemma-3-4b-pt mirror).

### Forward pass, softmax, sampling

**C12. The original Transformer turns the final hidden state into next-token probabilities with a linear layer followed by softmax, and shares that weight matrix with the input embedding.** VERIFIED.
Vaswani et al., "Attention Is All You Need", arXiv:1706.03762, Section 3.4. https://arxiv.org/abs/1706.03762
Quote: "the usual learned linear transformation and softmax function to convert the decoder output to predicted next-token probabilities".

**C13. At generation time, only the last position's logits are computed and used.** VERIFIED.
nanoGPT `model.py`, line 190: `logits = self.lm_head(x[:, [-1], :])`. https://github.com/karpathy/nanoGPT/blob/master/model.py

**C14. A decoder generates auto-regressively: each new token is fed back as input for the next step.** VERIFIED.
Vaswani et al., Section 3: "At each step the model is auto-regressive, consuming the previously generated symbols as additional input when generating the next."

**C15. Nucleus (top-p) sampling keeps the smallest set of tokens whose probabilities add up to at least p.** VERIFIED.
Holtzman et al., "The Curious Case of Neural Text Degeneration", ICLR 2020, arXiv:1904.09751. https://arxiv.org/abs/1904.09751
Quote: "the smallest set such that" the summed probability "≥ p".

**C16. Choosing the most likely text (greedy or beam search) produces bland, repetitive output. Sampling from the full distribution produces incoherent output because of an "unreliable tail".** VERIFIED.
Holtzman et al., abstract: "using likelihood as a decoding objective leads to text that is bland and strangely repetitive." Section 1 on the tail: "tens of thousands of candidate tokens with relatively low probability that are over-represented in the aggregate." Repetition feeds itself (Figure 4): "The probability of a repeated phrase increases with each repetition, creating a positive feedback loop."

**C17. No fixed k fits every step, because some distributions are flat and some are peaked.** VERIFIED.
Holtzman et al., Figure 5 caption: "flat distributions makes the use of a small k in top-k sampling problematic, while the presence of peaked distributions makes large k's problematic."

**C18. Min-p sampling scales its cutoff by the top token's probability, and Transformers and vLLM both support it.** VERIFIED.
Nguyen et al., arXiv:2407.01082. https://arxiv.org/abs/2407.01082

**C19. In Hugging Face Transformers, `generate()` defaults to greedy decoding (`do_sample: False`) with `max_length: 20`. The sampling defaults (temperature 1.0, top_k 50, top_p 1.0) only apply once sampling is switched on.** VERIFIED.
`src/transformers/generation/configuration_utils.py`, `_get_default_generation_params()`, main branch. https://github.com/huggingface/transformers/blob/main/src/transformers/generation/configuration_utils.py

**C20. A model's `generation_config.json` overrides those library defaults, and chat models ship with sampling turned on.** VERIFIED.
- Llama 3 8B Instruct: `do_sample: true, temperature: 0.6, top_p: 0.9`.
- Qwen2.5-7B-Instruct: `temperature: 0.7, top_p: 0.8, top_k: 20, repetition_penalty: 1.05`.
- Qwen3-8B: `temperature: 0.6, top_k: 20, top_p: 0.95`.
(Hugging Face repos cited in C9 and C10, plus Qwen/Qwen3-8B.)

**C21. Engines apply the samplers in different orders.** VERIFIED.
- Transformers applies temperature, then top-k, then top-p, then min-p (`generation/utils.py`, `_get_logits_processor`).
- vLLM v1 applies temperature, then min-p, then top-k/top-p (`vllm/v1/sample/sampler.py`, class docstring, steps 7b to 7d).
- llama.cpp's default chain is penalties, DRY, top-n-sigma, top-k, typical, top-p, min-p, XTC, and **temperature last** (`common/common.h`, `samplers` vector).
The same "temperature 0.8, top_p 0.95" therefore selects a different candidate set in llama.cpp than in Transformers.

**C22. llama.cpp's defaults are top_k 40, top_p 0.95, min_p 0.05, temp 0.80.** VERIFIED.
`common/common.h`, lines 230 to 236 (master, 24 Sep 2026). https://github.com/ggml-org/llama.cpp/blob/master/common/common.h

**C23. vLLM treats a temperature below 1e-5 as greedy (argmax), and never divides by zero.** VERIFIED.
`vllm/v1/sample/sampler.py`: `greedy_sample` returns `logits.argmax(dim=-1)`. The docstring's `temperature >= epsilon (1e-5)` sets the switch.

**C24. Temperature 0 is not deterministic on real servers. Across 1,000 completions at temperature 0 on Qwen3-235B-A22B-Instruct-2507, there were 80 distinct outputs. They were identical for 102 tokens and then diverged at token 103 ("Queens, New York" 992 times, "New York City" 8 times). With batch-invariant kernels, all 1,000 matched.** VERIFIED.
Horace He / Thinking Machines Lab, "Defeating Nondeterminism in LLM Inference", 10 Sep 2025. https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/
Quote: "the load (and thus batch-size) nondeterministically varies!"

**C25. `<|eot_id|>` and `<|im_end|>` are ordinary vocabulary entries. Generation stops when one of them is sampled. Llama 3 Instruct lists two EOS IDs, [128001, 128009], and Qwen2.5 Instruct lists [151645, 151643].** VERIFIED.
The models' `generation_config.json` files (C20).

### KV cache

**C26. Under causal masking, the keys and values of past tokens never change, so they can be cached. Without a cache, every step recomputes K and V for all previous tokens.** VERIFIED.
Hugging Face docs, "Cache explanation", `docs/source/en/cache_explanation.md`. https://huggingface.co/docs/transformers/en/cache_explanation
Its table: "for each step, recompute all previous K and V" vs "for each step, only compute current K and V".

**C27. nanoGPT's `generate()` uses no KV cache: it re-runs the whole sequence through the model on every step.** VERIFIED.
nanoGPT `model.py`, lines 306 to 331 (`logits, _ = self(idx_cond)` inside the loop).
Useful as the "before" code on screen.

**C28. For OPT-13B, the KV cache costs 800 KB per token, which is 1.6 GB for a single 2,048-token request. Systems before vLLM used only 20.4% to 38.2% of their KV memory for real token state.** VERIFIED.
Kwon et al., "Efficient Memory Management for Large Language Model Serving with PagedAttention", SOSP 2023, arXiv:2309.06180. https://arxiv.org/abs/2309.06180
Quote: "2 (key and value vectors) × 5120 (hidden state size) × 40 (number of layers) × 2 (bytes per FP16)". Modern models shrink this with grouped-query attention, where each KV head serves a group of query heads at close to multi-head quality (Ainslie et al., arXiv:2305.13245, https://arxiv.org/abs/2305.13245).



### Training and hallucination

**C29. The language-modelling objective factorises the probability of a text into a product of next-symbol conditionals.** VERIFIED.
GPT-2 paper, Eq. 1: p(x) = ∏ p(s_n | s_1, ..., s_{n-1}).

**C30. Training computes cross-entropy at every position in parallel (one next-token target per position), while generation uses only the last position.** VERIFIED.
nanoGPT `model.py`, line 187: `F.cross_entropy(logits.view(-1, logits.size(-1)), targets.view(-1), ignore_index=-1)`. Compare line 190 (C13).

**C31. Pretraining produces hallucinations as ordinary classification errors, and benchmarks that reward guessing over abstaining keep them alive.** VERIFIED.
Kalai, Nachum, Vempala, Zhang (OpenAI), "Why Language Models Hallucinate", arXiv:2509.04664. https://arxiv.org/abs/2509.04664
Quote: "language models are optimized to be good test-takers, and guessing when uncertain improves test performance."

**C32. The pretrained GPT-4 was well calibrated on MMLU, and post-training made its calibration much worse.** VERIFIED.
OpenAI, "GPT-4 Technical Report", arXiv:2303.08774, Figure 8. Quote: "The post-training hurts calibration significantly."

**C33. Mechanistic evidence shows a model choosing a rhyme word before it writes the line. Suppressing the planned word ("rabbit") makes it rewrite the line to end in "habit".** VERIFIED.
Lindsey et al. (Anthropic), "On the Biology of a Large Language Model", 2025. https://transformer-circuits.pub/2025/attribution-graphs/biology.html
Quote: "the model plans its outputs ahead of time when writing lines of poetry."

**C34. Models can recognise which letters are in a word but still miscount them. Errors track how many letters repeat, and word frequency has no significant effect.** VERIFIED.
Fu et al., "Why Do Large Language Models (LLMs) Struggle to Count Letters?", arXiv:2412.18626. https://arxiv.org/abs/2412.18626
Quote: "models are capable of recognizing the letters but not counting them".

### Token cost across languages

**C35. The same content translated into another language can take up to 15 times as many tokens. Even byte-level models show gaps of more than 4 times.** VERIFIED.
Petrov, La Malfa, Torr, Bibi, "Language Model Tokenizers Introduce Unfairness Between Languages", NeurIPS 2023, arXiv:2305.15425. https://arxiv.org/abs/2305.15425

**C36. On FLORES-200, cl100k_base (GPT-4) uses 4.79 times as many tokens for Hindi as for the same English sentences, and 8.34 times as many for Telugu. Measured in Unicode characters, the ratios are only 1.00 and 1.01.** MEASURED from primary data.
Source: the paper's released CSV, https://aleksandarpetrov.github.io/tokenization-fairness/assets/tokenization_lengths_validated.csv. The ratios match the paper's Appendix C table.
In other words, Telugu is about as long as English in characters but costs about 8 times the tokens. Full table in Section 2.

**C37. OpenAI's own tokenizer change cut the Indic token tax sharply. On FLORES-200 word fertility relative to English, Hindi went from 4.08x (cl100k) to 1.34x (o200k), and Telugu from 10.68x to 2.49x. The mean across ten Indian languages fell from 8.0x to 2.1x. The paper traces the tax to failed merges that leave single-byte tokens (r = 0.89).** VERIFIED; recent single-author preprint.
Srivastava, "The Tokenizer Tax", arXiv:2607.24276 (27 Jul 2026), Table 2. https://arxiv.org/abs/2607.24276
Caveat: its metric is tokens per whitespace word relative to English, which differs from Petrov's total-token ratio. Do not mix the two metrics in one chart.

**C38. Commercial APIs charge per token, and speakers of many languages pay more for worse results.** VERIFIED.
Ahia et al., "Do All Languages Cost the Same?", EMNLP 2023, arXiv:2305.13707. https://arxiv.org/abs/2305.13707
Quote: "speakers of a large number of the supported languages are overcharged while obtaining poorer results."

**C39. The Sarvam-1 tokenizer reports 1.4 to 2.1 tokens per word across its Indic languages, where it says other models need 4 to 8. Its vocabulary is 68,096.** PARTIAL (read through a summarising fetch).
https://www.sarvam.ai/blogs/sarvam-1

**C40. For one Telugu sentence, Gemma-3 needs 2.2 tokens per word, Llama-3 11.7 and Qwen2.5 10.0.** UNVERIFIED. The only source found is a Medium post using a single sentence. Measure it ourselves; do not cite.

Tally: 40 claims. 36 VERIFIED (C9 via an ungated mirror; C6 part-measured), 2 MEASURED from primary data or code (C7, C36), 1 PARTIAL (C39), 1 UNVERIFIED (C40).

---

## 2. Numbers worth showing

### Vocabulary sizes, which set the number of logits per step

| Tokenizer / model | Size | Source |
|---|---|---|
| GPT-2 (r50k_base) | 50,257 | tiktoken `openai_public.py` |
| cl100k_base (GPT-3.5/4) | 100,256 merges + specials to ID 100276 | tiktoken |
| o200k_base (GPT-4o) | 199,998 merges, specials 199999 and 200018 | tiktoken |
| gpt-oss-20b (config) | 201,088 | huggingface.co/openai/gpt-oss-20b `config.json` |
| Llama 3 | 128,256 (128,000 + 256 special) | Llama 3 paper; config |
| Qwen2.5 | 151,665 real; 152,064 padded in config | HF Qwen2.5-7B-Instruct |
| Qwen3-8B | 151,936 (config) | HF Qwen/Qwen3-8B |
| Gemma 2 | 256,000 (config) | unsloth/gemma-2-9b mirror |
| Gemma 3 | "262k" (paper); 262,208 (config) | arXiv:2503.19786 |
| Sarvam-1 | 68,096 | Sarvam blog (PARTIAL) |

### KV cache memory per token

Formula: bytes per token = 2 (K and V) × layers × KV heads × head_dim × bytes per element.

- **Llama 3 8B, bf16:** 32 layers, 8 KV heads (32 query heads), head_dim 4096/32 = 128. That gives 2 × 32 × 8 × 128 × 2 = **131,072 B = 128 KiB per token**, so **1 GiB at its 8,192-token context**. Without GQA (32 KV heads) it would be 512 KiB per token, 4 times as much. MEASURED from config.
- **Qwen2.5-7B, bf16:** 28 layers, 4 KV heads, head_dim 3584/28 = 128. That gives **57,344 B = 56 KiB per token**, or 1.75 GiB at 32K tokens. MEASURED from config.
- **OPT-13B (published):** 800 KB per token, 1.6 GB per 2,048-token request (vLLM paper, C28).
- **Waste before paging:** only 20.4% to 38.2% of KV memory held real tokens (C28).
- **Suggested on-screen line:** at 128 KiB per token, Llama 3 8B's KV cache for about 120K tokens takes as much memory as its roughly 16 GB of bf16 weights. This is a derived estimate; state the arithmetic on screen.

### Per-language token premium vs English, same FLORES-200 sentences

Petrov et al. data (C36): total tokens relative to English.

| Language | cl100k_base | GPT-2 | LLaMA (1) | Qwen-VL | BLOOM | MuRIL | UTF-8 bytes (ByT5) | Unicode chars |
|---|---|---|---|---|---|---|---|---|
| Hindi | 4.79 | 7.46 | 4.60 | 4.47 | 1.28 | 1.16 | 2.55 | 1.00 |
| Telugu | 8.34 | 13.09 | 10.71 | 7.06 | 1.33 | 1.21 | 2.68 | 1.01 |
| Tamil | 7.65 | 15.58 | 5.87 | 6.15 | 1.27 | 1.06 | 3.17 | 1.17 |
| Malayalam | 9.00 | 15.24 | 5.54 | 7.31 | 1.38 | 1.18 | 3.10 | 1.13 |
| Shan (worst) | 15.05 | 18.76 | 11.85 | 10.51 | 12.06 | n/a | 3.94 | 1.42 |

Srivastava 2026 (C37), word-fertility tax: Hindi cl100k 4.08x → o200k 1.34x; Telugu 10.68x → 2.49x; Malayalam 13.04x → 2.85x. Also: "At a fixed 8,192-token budget, Kannada and Telugu users receive only ~12% of the usable characters an English user does" (under cl100k).

Petrov et al. also found that for ChatGPT/GPT-4, "the cost to process a text in German or Italian is about 50% higher" than English.

### Default sampling parameters

| Library / model | Defaults |
|---|---|
| HF Transformers (no model config) | greedy (`do_sample=False`), max_length 20; if sampling: T 1.0, top_k 50, top_p 1.0 |
| llama.cpp `common.h` | T 0.80, top_k 40, top_p 0.95, min_p 0.05; temperature applied last |
| vLLM v1 | T < 1e-5 → argmax |
| Llama 3 8B Instruct | T 0.6, top_p 0.9 |
| Qwen2.5-7B-Instruct | T 0.7, top_p 0.8, top_k 20, rep. penalty 1.05 |
| Qwen3-8B | T 0.6, top_p 0.95, top_k 20 |
| GPT-2 era (Alammar) | top_k 40 described as the "middle ground" |

### Other figures

- **Temperature 0 on a real server:** 80 distinct completions out of 1,000; divergence at token 103 (C24).
- **Llama 3 English compression:** 3.94 characters per token, up from 3.17 in Llama 2 (C8).
- **Nucleus size:** Holtzman et al. put it at "between one and a thousand candidates" per step.

---

## 3. What the best existing content covers and misses

View counts were read from YouTube watch pages on 24 Sep 2026. Coverage notes come from knowledge of the videos plus the checks named below. Re-watch anything before quoting it on screen.

**3Blue1Brown, "Transformers, the tech behind LLMs", Deep Learning Ch. 5** (Apr 2024, 27 min, 11.2M views). Also "Attention in transformers, step-by-step", Ch. 6 (4.6M), and "Large Language Models explained briefly" (Nov 2024, 8 min, 7.7M).
- Brilliant at: embeddings as directions in space, the unembedding matrix, the predict-sample-repeat loop, softmax with temperature drawn as a distribution reshaping, and the GPT-3 parameter count.
- Leaves out or simplifies: tokens are largely treated as words. There is no BPE mechanics, no top-p or top-k, no KV cache, no inference cost, and no measurement on a model you can run.

**Andrej Karpathy, "[1hr Talk] Intro to Large Language Models"** (Nov 2023, 60 min, 4.1M views).
- Brilliant at: "two files" (weights plus a run loop), next-word prediction as lossy compression, "dreaming" documents as the root of hallucination, and the LLM-as-OS framing.
- Leaves out: tokenization details, sampling mechanics, and the KV cache. It is a conceptual talk with no measurements.

**Karpathy, "Let's build GPT: from scratch, in code, spelled out."** (Jan 2023, 1h56m, 7.9M views).
- Brilliant at: training with cross-entropy, causal masking, and the full code path.
- Leaves out: it uses a character-level tokenizer, not BPE. Its generate loop, like nanoGPT's (C27), has no KV cache. Sampling is plain multinomial with optional top-k.

**Karpathy, "Let's build the GPT Tokenizer"** (Feb 2024, 2h13m, 1.2M views).
- Brilliant at: this is the definitive BPE deep dive. It builds minbpe, covers the regex pre-split, special tokens, and why many LLM oddities trace back to the tokenizer.
- Leaves out: it runs 2h13m, it is not about generation, and it has no systematic per-language cost measurement for Indian languages.

**Karpathy, "Deep Dive into LLMs like ChatGPT"** (Feb 2025, 3h31m, 9.7M views).
- Brilliant at: the full pipeline from pretraining to RL, tokens shown in a live tokenizer UI, hallucination and its mitigations, and "models need tokens to think".
- Leaves out: it is 3.5 hours. Sampler ordering, nondeterminism at temperature 0, and KV-cache memory are not its focus.

**Jay Alammar, "The Illustrated GPT-2"** (blog).
- Brilliant at: pictures of masked self-attention. It covers the KV cache in words ("GPT-2 holds on to the key and value vectors") and top_k = 40.
- Leaves out: the author notes he "used 'words' and 'tokens' interchangeably". There is no top-p, no memory arithmetic and no multilingual cost. It dates from the GPT-2 era.

### Gaps our episode can fill, all measurable on a real open model

1. **The whole distribution, live.** Show the actual 128,256 logits from Llama 3 8B at one step: the top 20, the long tail's total mass, and the same step at T = 0.2, 0.7 and 1.5. Most explainers draw 5 bars.
2. **Sampler order is not standard.** Same model, same "T 0.8, top_p 0.95", but a different candidate set in llama.cpp (temperature last) than in Transformers (temperature first). Count the surviving tokens in both. We found no popular explainer that mentions this.
3. **Temperature 0 is not deterministic.** Reproduce the Thinking Machines effect locally: the same prompt, greedy, at batch size 1 vs a mixed batch in vLLM. Show the first diverging token.
4. **The KV cache with a stopwatch and a memory gauge.** Time to first token vs time per later token, `use_cache=False` vs `True`, plus the 128 KiB-per-token arithmetic for Llama 3 8B.
5. **The Telugu and Hindi token tax, measured.** One paragraph in English, Hindi and Telugu, tokenized with cl100k, o200k, Llama 3, Qwen2.5 and Gemma 3. Show the byte-fallback mechanism: Telugu is almost the same length as English in characters but costs about 8x the tokens under cl100k. Then show what that does to the price and the usable context.
6. **The leading-space trap.** "strawberry" is 3 tokens but " strawberry" is 1, and cl100k and o200k split it differently (C7).
7. **EOS is just a token.** Plot the probability of `<|eot_id|>` at each step of a real answer. Stopping is a sample like any other.
8. **Fluency is low loss, not truth.** Show per-token cross-entropy (surprisal) on a true sentence and on a false but fluent one. The model scores both as fluent.

---

## 4. Common misconceptions

1. **"Temperature 0 is deterministic."**
   The sampler is deterministic: argmax (vLLM `greedy_sample`, C23). The numbers going into it are not, because kernels vary with batch size, and batch size varies with server load. Result: 80 distinct outputs in 1,000 runs (C24).
   Nuance: on one machine at a fixed batch size it is usually reproducible, and batch-invariant kernels make it exact.

2. **"The model sees letters or words."**
   It sees token IDs. "strawberry" is `str|aw|berry` (cl100k), and " strawberry" is a single ID (C7).
   Nuance: models can often spell a word correctly, so letter identity is partly learned. The documented failure is counting repeated letters (C34). Tokenization is part of the cause, not all of it.

3. **"The model outputs a word."**
   It outputs one logit per vocabulary entry, 128,256 of them for Llama 3, and the sampler, which is ordinary code, picks one (C12, C13, C9).

4. **"It only thinks one token ahead."**
   Tokens are emitted one at a time and never revised, but its internal state can hold plans: rhyme targets are chosen before the line starts (C33).
   Nuance: this was shown for particular circuits in one model family. Do not generalise it to "plans whole answers".

5. **"Greedy gives the best answer."**
   For open-ended text, maximising likelihood produces repetitive degeneration, and the loop reinforces itself (C16).
   Nuance: for short factual or code answers, greedy or low temperature is often the right choice. Model vendors ship sampling on by default (C20).

6. **"temperature/top_p mean the same thing everywhere."**
   Defaults differ (C19, C20, C22) and so does the order (C21). Transformers with no model config does not sample at all and stops at 20 tokens (C19).

7. **"Hallucination is a bug, and temperature 0 fixes it."**
   Greedy decoding picks the most likely continuation. When the model does not know the answer, that is still a guess. Training and evaluation reward guessing (C31), and post-training can make confidence less calibrated (C32).
   Nuance: lower temperature does reduce sampling errors in the tail. It cannot fix knowledge the weights do not hold.

8. **"A token is about 4 characters in any language."**
   That holds for English-heavy text (C4, C8). Under cl100k, Telugu costs 8.34x the English token count for the same meaning at essentially the same character count (C36).
   Nuance: newer tokenizers (o200k, Gemma 3) shrink this gap a lot (C37, C11), so always name the tokenizer.

9. **"The KV cache makes long context free."**
   It removes recomputation (C26), but memory grows linearly with tokens: 128 KiB per token on Llama 3 8B, 800 KB on OPT-13B. Each new token still attends over the whole cache (C28). Memory, not compute, limits how many users a GPU can serve.

---

## 5. Suggested angle

The network never writes text. On every step it outputs a vector of 128,256 scores (Llama 3), one per token fragment, and two pieces of ordinary code on either side of it decide nearly everything a developer notices: the tokenizer before the network and the sampler after it. The tokenizer decides what the model can see, which is why "strawberry" is three unrelated IDs but " strawberry" is one, and why the same sentence in Telugu costs about 8 times the English tokens under GPT-4's tokenizer while having about the same number of characters. The sampler decides what you get: its defaults and even its order of operations differ between Transformers and llama.cpp, and "temperature 0" still produced 80 different answers in 1,000 runs because of batch-size effects in the numbers feeding it. Build the episode as "one forward pass, then a function you could have written yourself", and prove each claim with a live measurement on an open model. That is exactly what the illustrated explainers do not do.

## Revisions after review (24 Sep 2026)

Three critics (fact-checker, senior engineer, confused viewer) reviewed the first cut. What changed, and why:

| Claim in the first cut | Problem found | Now |
|---|---|---|
| Transformers keeps 6, llama.cpp 10 (T 0.8, min_p 0.05) | bf16 logits; with the output layer in fp32 llama.cpp keeps 12, and its 12th token clears the cutoff by 0.01% | T 0.7, min_p 0.07: 4 vs 8, no token within 8% of a cutoff; llama.cpp keeps more in 15 of 15 settings; Transformers side asserted against its own processors |
| Batch of 4 mixed prompts shifted scores by 0.27, output identical | Left padding without position ids: padding and RoPE offset confounded with batch size | Identical rows, no padding, batch 1 to 64: scores move by up to 0.25 and 512-token greedy text splits at token 19 (batch 2) or 38 (4, 8, 32, 64); batch 16 identical; batch 1 repeats exactly |
| 347 x 29: 0 of 100, "predicting what an answer looks like, not computing one" | One problem sampled at T 0.8; every answer ended in the right digit | 200 random problems, greedy: 65 exact; last digit 97.5%, leading digits 87 to 98%, middle digits 43 to 45%; instruct model 55 direct, 83 with working |
| "Fluent is not true": water 2.10 vs 2.30 mean loss | Three hand pairs, mean over unequal token counts, and the model preferred truth in all three | Geometry of Truth cities: 747 of 748 prefer the true country (median margin 8.9 nats); TruthfulQA: true answer preferred in 33.2% of 790 |
| Context: interface flips issues (65%) to Create (49%) | No control for "Create is just conventional" | Renaming the method to MintCreditNote makes it write Mint (46%) |
| KV cache 66 vs 28 tok/s, "the gap grows" | Two points, no warm-up | Median of 5 after warm-up at 32 to 1,024 tokens: 1.0x, 1.6x, 4.0x, 6.9x; measured bandwidth 329 GB/s gives a 106 tok/s ceiling against 69 measured |
| 185 of 200 continuations distinct | Meaningless at 6 new tokens | First-token counts against the softmax prediction (space 61 vs 73, "the" 44 vs 43) |
| 896 megabytes at 32,000 tokens | MiB at 32,768 | 940 MB at 32,768 tokens |
| Temperature 0 "shifted the scores by 0.27" (on screen) | Temperature does not change logits | "batch size alone changed greedy output at token 19" |
