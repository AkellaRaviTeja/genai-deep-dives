"""Experiments for "What an LLM actually does". Every number the episode shows
comes from a run of this file, written to episodes/llm-geek/data/*.json.

    uv run python llm_experiments.py            all experiments
    uv run python llm_experiments.py tokenizers one of them

The model is Qwen2.5-1.5B (the base model, not the chat one): open weights,
small enough for an 8 GB laptop GPU, and big enough for its distributions to
mean something. Runs are seeded, and each JSON records how it was produced.
"""

import json, math, sys, time, platform, datetime, pathlib, statistics
from collections import Counter

import torch
import tiktoken
from transformers import AutoTokenizer, AutoModelForCausalLM, __version__ as TF_VERSION

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "results" / "llm"
OUT.mkdir(parents=True, exist_ok=True)
MODEL = "Qwen/Qwen2.5-1.5B"
DEV = "cuda" if torch.cuda.is_available() else "cpu"


def meta(extra=None):
    return {
        "model": MODEL,
        "torch": torch.__version__,
        "transformers": TF_VERSION,
        "device": torch.cuda.get_device_name(0)
        if DEV == "cuda"
        else platform.processor(),
        "dtype": "bfloat16",
        "run_at": datetime.datetime.now().isoformat(timespec="seconds"),
        **(extra or {}),
    }


def save(name, payload):
    path = OUT / f"{name}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    print(f"  wrote {path.relative_to(ROOT)}")


_model = _tok = None


def model():
    global _model, _tok
    if _model is None:
        _tok = AutoTokenizer.from_pretrained(MODEL)
        _model = (
            AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16)
            .to(DEV)
            .eval()
        )
    return _model, _tok


def piece(tok, i):
    """How a token id reads on screen: its text, with the leading space made visible."""
    s = tok.decode([i])
    return s.replace(" ", "␣") if s.strip() == "" or s.startswith(" ") else s


_head32 = None


@torch.no_grad()
def next_logits(prompt):
    """The final scores for the next token, with the last matrix multiply in float32.
    The network runs in bfloat16, whose logits come in steps of up to 0.125 at this
    size; redoing only the output layer in fp32 keeps small differences real."""
    global _head32
    m, tok = model()
    if _head32 is None:
        _head32 = m.lm_head.weight.float()
    ids = tok(prompt, return_tensors="pt").input_ids.to(DEV)
    h = m.model(ids).last_hidden_state[0, -1].float()
    return (_head32 @ h).cpu(), ids[0].tolist()


def top(logits, k, tok, temperature=1.0):
    probs = torch.softmax(logits / temperature, dim=-1)
    p, i = probs.topk(k)
    return [
        {
            "id": int(a),
            "text": piece(tok, int(a)),
            "logit": round(float(logits[a]), 3),
            "p": round(float(b), 5),
        }
        for a, b in zip(i, p)
    ]


# ---- 1. tokenizers -----------------------------------------------------------------------
def tokenizers():
    en = (ROOT / "corpus/udhr_eng.txt").read_text()
    docs = {
        l: (ROOT / f"corpus/udhr_{l}.txt").read_text() for l in ["eng", "tel", "hin"]
    }
    sentence = {
        "eng": "The invoice total is one thousand three hundred and fifty rupees.",
        "tel": "ఇన్వాయిస్ మొత్తం వెయ్యి మూడు వందల యాభై రూపాయలు.",
        "hin": "इनवॉइस की कुल राशि एक हज़ार तीन सौ पचास रुपये है।",
    }
    probes = [
        "strawberry",
        " strawberry",
        "Strawberry",
        " STRAWBERRY",
        "1350",
        " 1,350",
        "Refund",
        " RefundInvoice",
    ]
    rows = []

    def add(name, family, encode, decode_one, vocab):
        r = {
            "name": name,
            "family": family,
            "vocab": vocab,
            "udhr_tokens": {},
            "sentence": {},
            "probes": {},
        }
        for l, d in docs.items():
            r["udhr_tokens"][l] = len(encode(d))
        for l, s in sentence.items():
            ids = encode(s)
            r["sentence"][l] = {
                "count": len(ids),
                "pieces": [decode_one(i) for i in ids],
            }
        for p in probes:
            ids = encode(p)
            r["probes"][p] = {"ids": ids, "pieces": [decode_one(i) for i in ids]}
        r["ratio_vs_english"] = {
            l: round(r["udhr_tokens"][l] / r["udhr_tokens"]["eng"], 2) for l in docs
        }
        rows.append(r)
        print(
            f"  {name:<22} vocab {vocab:>7}  UDHR tokens en {r['udhr_tokens']['eng']:>6}  te {r['udhr_tokens']['tel']:>6} ({r['ratio_vs_english']['tel']}x)  hi {r['udhr_tokens']['hin']:>6} ({r['ratio_vs_english']['hin']}x)"
        )

    for enc_name, family in [
        ("o200k_base", "OpenAI GPT-4o and later"),
        ("cl100k_base", "OpenAI GPT-4, GPT-3.5"),
    ]:
        e = tiktoken.get_encoding(enc_name)
        add(
            enc_name,
            family,
            lambda s, e=e: e.encode(s),
            lambda i, e=e: e.decode_single_token_bytes(i).decode("utf-8", "replace"),
            e.n_vocab,
        )
    for repo, family in [
        (MODEL, "Qwen2.5"),
        ("deepseek-ai/DeepSeek-V3", "DeepSeek-V3"),
        ("microsoft/Phi-3.5-mini-instruct", "Phi-3.5"),
        ("HuggingFaceTB/SmolLM2-1.7B", "SmolLM2"),
        ("sarvamai/sarvam-1", "Sarvam-1 (built for Indian languages)"),
    ]:
        try:
            t = AutoTokenizer.from_pretrained(repo)
        except Exception as ex:  # gated or unavailable: recorded, not fatal
            print(f"  {repo}: skipped ({str(ex).splitlines()[0][:90]})")
            continue
        add(
            repo.split("/")[1],
            family,
            lambda s, t=t: t.encode(s, add_special_tokens=False),
            lambda i, t=t: t.decode([i]),
            len(t),
        )
    if len(rows) < 3:
        raise SystemExit(f"only {len(rows)} tokenizers loaded; need at least 3")
    save(
        "tokenizers",
        {
            "meta": meta(
                {
                    "corpus": "Universal Declaration of Human Rights, unicode-org/udhr on GitHub (eng, tel, hin)",
                    "corpus_words": {l: len(d.split()) for l, d in docs.items()},
                    "corpus_bytes": {l: len(d.encode()) for l, d in docs.items()},
                }
            ),
            "sentence": sentence,
            "tokenizers": rows,
        },
    )


# ---- 2 and 3. next-token distribution, softmax, temperature --------------------------------
def distribution():
    m, tok = model()
    prompt = "The invoice total is"
    logits, ids = next_logits(prompt)
    probs = torch.softmax(logits, -1)
    entropy = float(-(probs * torch.log2(probs.clamp_min(1e-12))).sum())
    temps = {}
    for T in [0.2, 0.7, 1.0, 1.5]:
        pT = torch.softmax(logits / T, -1)
        sorted_p = pT.sort(descending=True).values
        nucleus = int((sorted_p.cumsum(0) < 0.9).sum()) + 1
        temps[str(T)] = {"top": top(logits, 8, tok, T), "top_p_0_9_size": nucleus}
    print(
        f"  '{prompt}' -> top {top(logits, 3, tok)[0]['text']!r}, entropy {entropy:.2f} bits, vocab {logits.numel()}"
    )
    save(
        "distribution",
        {
            "meta": meta(),
            "prompt": prompt,
            "prompt_ids": ids,
            "prompt_pieces": [piece(tok, i) for i in ids],
            "vocab_size": logits.numel(),
            "top": top(logits, 12, tok),
            "min_logit": round(float(logits.min()), 2),
            "max_logit": round(float(logits.max()), 2),
            "tokens_over_1pct": int((probs > 0.01).sum()),
            "entropy_bits": round(entropy, 3),
            "temperatures": temps,
        },
    )


# ---- 4. many samples ----------------------------------------------------------------------------
@torch.no_grad()
def samples():
    """200 samples at temperature 0.8: how often each first token came out, against
    the share the softmax predicted for it."""
    m, tok = model()
    prompt, T, n, new = "The invoice total is", 0.8, 200, 6
    torch.manual_seed(1234)
    ids = tok(prompt, return_tensors="pt").input_ids.to(DEV)
    rows = []
    for start in range(0, n, 50):
        rows += m.generate(ids.repeat(50, 1), do_sample=True, temperature=T, top_p=1.0, top_k=0,
                           max_new_tokens=new, pad_token_id=tok.eos_token_id)[:, ids.shape[1]:].tolist()
    logits, _ = next_logits(prompt)
    pred = torch.softmax(logits / T, -1)
    first = Counter(r[0] for r in rows)
    table = [{"text": piece(tok, i), "observed": c, "predicted": round(float(pred[i]) * n, 1)}
             for i, c in first.most_common(10)]
    greedy = tok.decode(m.generate(ids, do_sample=False, max_new_tokens=new, pad_token_id=tok.eos_token_id)[0][ids.shape[1]:],
                        skip_special_tokens=True)
    greedy_ids = m.generate(ids, do_sample=False, max_new_tokens=new, pad_token_id=tok.eos_token_id)[0][ids.shape[1]:].tolist()
    print("  first token, observed vs predicted of 200: " + ", ".join(f"{r['text']!r} {r['observed']}/{r['predicted']}" for r in table[:5]))
    save("samples", {"meta": meta({"seed": 1234}), "prompt": prompt, "temperature": T, "n": n,
                     "first_token": table, "distinct_first_tokens": len(first),
                     "greedy": greedy, "greedy_pieces": [piece(tok, i) for i in greedy_ids],
                     "examples": [tok.decode(r, skip_special_tokens=True) for r in rows[:24]]})


# ---- 4b. arithmetic --------------------------------------------------------------------------------
@torch.no_grad()
def arithmetic():
    """200 random 3-digit x 2-digit problems, greedy, few-shot, on the base model:
    accuracy of the whole answer and of each digit. Then the same problems on the
    instruct model, once answering directly and once writing its working."""
    import random, re
    m, tok = model()
    rng = random.Random(7)
    probs = [(rng.randint(100, 999), rng.randint(10, 99)) for _ in range(200)]
    shots = "Q: What is 23 times 17?\nA: 391\nQ: What is 58 times 12?\nA: 696\n"

    def digits_right(ans, want):
        a, w = ans.rjust(len(want), "?")[-len(want):], want
        return [x == y for x, y in zip(a[::-1], w[::-1])]  # from the last digit

    def batch_gen(mm, tt, prompts, new):
        tt.padding_side = "left"
        out = []
        for i in range(0, len(prompts), 25):
            enc = tt(prompts[i:i + 25], return_tensors="pt", padding=True).to(DEV)
            g = mm.generate(**enc, do_sample=False, max_new_tokens=new, pad_token_id=tt.eos_token_id)
            out += [tt.decode(r[enc.input_ids.shape[1]:], skip_special_tokens=True) for r in g]
        return out

    def score(answers):
        right, pos = 0, [[0, 0] for _ in range(5)]
        for (a, b), ans in zip(probs, answers):
            want = str(a * b)
            if ans == want:
                right += 1
            for k, ok in enumerate(digits_right(ans, want)):
                pos[k][0] += ok; pos[k][1] += 1
        return right, [round(r / t, 3) for r, t in pos if t]

    def first_number(t):
        mm = re.search(r"-?\d[\d,]*", t)
        return mm.group(0).replace(",", "") if mm else ""

    base = [first_number(t.split("\n")[0]) for t in batch_gen(m, tok, [f"{shots}Q: What is {a} times {b}?\nA:" for a, b in probs], 8)]
    b_right, b_pos = score(base)
    print(f"  base, greedy: {b_right}/200 exact; per digit from the last: {b_pos}")

    # the original single problem, sampled 100 times, kept for the picture
    torch.manual_seed(1234)
    one = f"{shots}Q: What is 347 times 29?\nA:"
    ids = tok(one, return_tensors="pt").input_ids.to(DEV)
    texts = []
    for _ in range(2):
        g = m.generate(ids.repeat(50, 1), do_sample=True, temperature=0.8, top_p=1.0, top_k=0, max_new_tokens=6, pad_token_id=tok.eos_token_id)
        texts += [first_number(tok.decode(r[ids.shape[1]:], skip_special_tokens=True)) or "(none)" for r in g]
    answers = Counter(texts)
    greedy_one = first_number(tok.decode(m.generate(ids, do_sample=False, max_new_tokens=6, pad_token_id=tok.eos_token_id)[0][ids.shape[1]:], skip_special_tokens=True))

    # instruct model: direct answer, and with room to work
    inst_name = MODEL + "-Instruct"
    it = AutoTokenizer.from_pretrained(inst_name)
    global _head32
    m.to("cpu"); _head32 = None; torch.cuda.empty_cache()  # two 3 GB models do not fit in 8 GB together
    im = AutoModelForCausalLM.from_pretrained(inst_name, dtype=torch.bfloat16).to(DEV).eval()
    def chat(q):
        return it.apply_chat_template([{"role": "user", "content": q}], tokenize=False, add_generation_prompt=True)
    direct = [first_number(t) for t in batch_gen(im, it, [chat(f"What is {a} times {b}? Reply with only the number.") for a, b in probs], 10)]
    d_right, d_pos = score(direct)
    worked_txt = batch_gen(im, it, [chat(f"What is {a} times {b}? Work it out step by step, then give the final answer on the last line as 'Answer: <number>'.") for a, b in probs], 320)
    def final(t):
        mm = re.findall(r"Answer:\s*\**\s*(-?[\d,]+)", t)
        return mm[-1].replace(",", "") if mm else (re.findall(r"-?\d[\d,]*", t) or [""])[-1].replace(",", "")
    worked = [final(t) for t in worked_txt]
    w_right, w_pos = score(worked)
    print(f"  instruct, direct: {d_right}/200; with working: {w_right}/200")
    del im; torch.cuda.empty_cache(); m.to(DEV)
    save("arithmetic", {"meta": meta({"seed": 7, "instruct_model": inst_name}),
        "problems": len(probs), "shots": shots,
        "base_greedy": {"exact": b_right, "digit_accuracy_from_last": b_pos},
        "instruct_direct": {"exact": d_right, "digit_accuracy_from_last": d_pos},
        "instruct_worked": {"exact": w_right, "digit_accuracy_from_last": w_pos, "example": worked_txt[0]},
        "one_problem": {"q": "347 x 29", "correct": "10063", "greedy": greedy_one, "n": 100, "temperature": 0.8,
                        "answers": answers.most_common(), "correct_share": answers.get("10063", 0) / 100,
                        "last_digit_3": sum(a.endswith("3") for a in texts)},
        "examples": [{"q": f"{a} x {b}", "want": str(a * b), "base": x, "worked": y} for (a, b), x, y in list(zip(probs, base, worked))[:12]]})


# ---- 4c. the chat template ------------------------------------------------------------------------
def chat_template():
    """What a chat model actually receives: the conversation flattened into one text."""
    it = AutoTokenizer.from_pretrained(MODEL + "-Instruct")
    msgs = [{"role": "system", "content": "You are a billing assistant."},
            {"role": "user", "content": "What is the total on invoice 4471?"}]
    text = it.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    ids = it(text).input_ids
    print(f"  {len(ids)} tokens:\n{text}")
    save("chat_template", {"meta": meta({"tokenizer": MODEL + "-Instruct"}), "messages": msgs, "text": text, "tokens": len(ids)})


# ---- 5. context changes the prediction --------------------------------------------------------------
def context():
    """The same handler line, with and without the service's interface in the file.
    The struct declares svc as an InvoiceService, so the model can only know what
    that service offers if the interface is in the context."""
    m, tok = model()
    iface = ("// InvoiceService is the only place that touches the database.\n"
             "type InvoiceService interface {\n\tGet(ctx context.Context, id int64) (Invoice, error)\n"
             "\tList(ctx context.Context, f Filter) ([]Invoice, error)\n"
             "\tCreateCreditNote(ctx context.Context, invoiceID int64, cents int64, reason string) (CreditNote, error)\n}\n\n")
    head = "package api\n\nimport (\n\t\"context\"\n\t\"net/http\"\n)\n\n"
    body = ("type InvoiceHandler struct {\n\tsvc InvoiceService\n}\n\n"
            "// Refund issues a credit note for an invoice.\n"
            "func (h *InvoiceHandler) Refund(w http.ResponseWriter, r *http.Request) {\n"
            "\tid, err := parseID(r)\n\tif err != nil {\n\t\thttp.Error(w, \"bad invoice id\", http.StatusBadRequest)\n\t\treturn\n\t}\n"
            "\tnote, err := h.svc.")
    res = {}
    renamed = iface.replace("CreateCreditNote", "MintCreditNote")
    for key, prompt in [("without_interface", head + body), ("with_interface", head + iface + body),
                        ("with_renamed_method", head + renamed + body)]:
        logits, ids = next_logits(prompt)
        pids = tok(prompt, return_tensors="pt").input_ids.to(DEV)
        with torch.no_grad():
            g = m.generate(pids, do_sample=False, max_new_tokens=14, pad_token_id=tok.eos_token_id)[0][pids.shape[1]:]
        res[key] = {"prompt_tokens": len(ids), "top": top(logits, 8, tok), "greedy": tok.decode(g, skip_special_tokens=True).split("\n")[0]}
        print(f"  {key}: {res[key]['top'][0]['text']!r} {res[key]['top'][0]['p']:.2f}, {res[key]['top'][1]['text']!r} {res[key]['top'][1]['p']:.2f}; writes {res[key]['greedy']!r}")
    save("context", {"meta": meta(), "file_head": head, "interface": iface, "renamed_interface": renamed, "handler": body, **res})

# ---- 6. is greedy decoding deterministic? -------------------------------------------------------------
@torch.no_grad()
def determinism():
    """The same prompt, copied into batches of 1 to 64 rows: no padding, so every row
    is bit-for-bit the same input at the same positions. Only the batch size changes,
    and with it the GPU kernels chosen for the matrix multiplies."""
    m, tok = model()
    prompt = "The invoice total is"
    ids = tok(prompt, return_tensors="pt").input_ids.to(DEV)
    NEW = 512
    def run(bs):
        l = m(ids.repeat(bs, 1)).logits[0, -1].float()
        g = m.generate(ids.repeat(bs, 1), do_sample=False, max_new_tokens=NEW, min_new_tokens=NEW, pad_token_id=tok.eos_token_id)[:, ids.shape[1]:]
        return l, g
    l1, g1 = run(1)
    ref = g1[0].tolist()
    repeat = len({tuple(run(1)[1][0].tolist()) for _ in range(5)} | {tuple(ref)})
    rows = []
    for bs in [1, 2, 4, 8, 16, 32, 64]:
        l, g = run(bs)
        rows_same = len({tuple(r) for r in g.tolist()})
        row0 = g[0].tolist()
        first = next((i for i, (x, y) in enumerate(zip(ref, row0)) if x != y), None)
        rows.append({"batch": bs, "max_logit_diff_vs_1": round(float((l - l1).abs().max()), 4),
                     "first_token_that_differs_from_batch_1": first, "rows_identical_within_batch": rows_same == 1,
                     "text_at_divergence": tok.decode(row0[max(0, (first or 0) - 6):(first or 0) + 8]) if first is not None else None,
                     "text_batch_1": tok.decode(ref[max(0, (first or 0) - 6):(first or 0) + 8]) if first is not None else None})
        print(f"  batch {bs:>2}: max logit diff {rows[-1]['max_logit_diff_vs_1']:.4f}; first differing token {first}")
    print(f"  batch 1 repeated 6 times: {repeat} distinct output(s)")
    save("determinism", {"meta": meta({"new_tokens": NEW}), "prompt": prompt, "batch_1_repeated_6_distinct": repeat,
                         "max_logit": round(float(l1.max()), 2), "top2_gap": round(float(l1.topk(2).values[0] - l1.topk(2).values[1]), 3),
                         "batches": rows})


# ---- 7. the KV cache ------------------------------------------------------------------------------------
@torch.no_grad()
def kvcache():
    m, tok = model()
    cfg = m.config
    head_dim = cfg.hidden_size // cfg.num_attention_heads
    per_token = 2 * cfg.num_hidden_layers * cfg.num_key_value_heads * head_dim * 2  # K and V, bf16 = 2 bytes
    per_token_mha = 2 * cfg.num_hidden_layers * cfg.num_attention_heads * head_dim * 2
    weight_bytes = sum(p.numel() * p.element_size() for p in m.parameters())
    sync = (lambda: torch.cuda.synchronize()) if DEV == "cuda" else (lambda: None)
    # the card's real memory bandwidth: copy 1 GiB on the device, read + write
    x = torch.empty(2**29, dtype=torch.bfloat16, device=DEV); y = torch.empty_like(x)
    bw = []
    for _ in range(10):
        sync(); t0 = time.perf_counter(); y.copy_(x); sync(); bw.append(2 * x.numel() * 2 / (time.perf_counter() - t0))
    del x, y; torch.cuda.empty_cache()
    bandwidth = statistics.median(bw)
    ids = tok("The invoice total is", return_tensors="pt").input_ids.to(DEV)
    def timed(n, use):
        sync(); t0 = time.perf_counter()
        m.generate(ids, do_sample=False, max_new_tokens=n, min_new_tokens=n, use_cache=use, pad_token_id=tok.eos_token_id)
        sync(); return time.perf_counter() - t0
    timed(16, True); timed(16, False)  # warm-up
    res = []
    for n in [32, 128, 512, 1024]:
        on = statistics.median(timed(n, True) for _ in range(5))
        off = statistics.median(timed(n, False) for _ in range(3 if n >= 512 else 5))
        res.append({"tokens": n, "cache_tok_s": round(n / on, 1), "no_cache_tok_s": round(n / off, 1), "speedup": round(off / on, 2)})
        print(f"  {n:>5} tokens: cache {n / on:6.1f} tok/s, no cache {n / off:6.1f} tok/s ({off / on:.1f}x)")
    ceiling = bandwidth / weight_bytes
    print(f"  bandwidth {bandwidth / 1e9:.0f} GB/s; weights {weight_bytes / 1e9:.2f} GB; ceiling {ceiling:.0f} tok/s")
    save("kvcache", {"meta": meta(), "layers": cfg.num_hidden_layers, "attention_heads": cfg.num_attention_heads,
                     "kv_heads": cfg.num_key_value_heads, "head_dim": head_dim, "bytes_per_token": per_token,
                     "bytes_per_token_without_gqa": per_token_mha, "mb_per_1k_tokens": round(per_token * 1000 / 2**20, 1),
                     "mb_at_32k_tokens": round(per_token * 32768 / 2**20, 1), "weight_bytes": weight_bytes,
                     "measured_bandwidth_gb_s": round(bandwidth / 1e9, 1), "ceiling_tok_s": round(ceiling, 1), "timing": res})


# ---- 8. surprise per token: the training signal ---------------------------------------------------------
@torch.no_grad()
def surprise():
    m, tok = model()
    text = "The invoice total is $1,350.00, due on 15 October. Please pay by bank transfer to account 4471-0932."
    ids = tok(text, return_tensors="pt").input_ids.to(DEV)
    logits = m(ids).logits[0, :-1].float()
    lp = torch.log_softmax(logits, -1)
    target = ids[0, 1:]
    nll = -lp[torch.arange(len(target)), target]
    rows = [
        {
            "text": piece(tok, int(t)),
            "loss": round(float(l), 3),
            "p": round(math.exp(-float(l)), 4),
        }
        for t, l in zip(target, nll)
    ]
    hardest = sorted(rows, key=lambda r: -r["loss"])[:3]
    print(
        f"  mean loss {float(nll.mean()):.2f} nats over {len(rows)} tokens; hardest: {[h['text'] for h in hardest]}"
    )
    save(
        "surprise",
        {
            "meta": meta(),
            "text": text,
            "first": piece(tok, int(ids[0, 0])),
            "tokens": rows,
            "mean_loss": round(float(nll.mean()), 3),
            "account_digits_mean_loss": round(statistics.mean(r["loss"] for r in rows[[r["text"] for r in rows].index("␣account") + 1:] if r["text"].strip().isdigit()), 3),
            "ln10": round(math.log(10), 3),
        },
    )


# ---- 9. same settings, different engines -----------------------------------------------------------
def samplers():
    """Transformers applies temperature, then top-k, then top-p, then min-p.
    llama.cpp applies top-k, top-p and min-p first and temperature LAST.
    Same model, same logits, same settings: count the tokens each keeps."""
    m, tok = model()
    logits, _ = next_logits("The invoice total is")
    # Settings chosen so that no token sits within 8% of a cutoff in either order
    # (at min_p 0.05 llama.cpp's twelfth token clears it by 0.01%); the sweep below
    # shows the direction of the gap holds at every setting.
    T, K, P, MINP = 0.7, 40, 0.95, 0.07

    def top_k(l, k):
        v = l.topk(k).values[-1]
        return torch.where(l >= v, l, torch.full_like(l, float("-inf")))
    def top_p(l, p):
        probs = torch.softmax(l, -1)
        sp, si = probs.sort(descending=True)
        keep = sp.cumsum(0) - sp < p
        mask = torch.zeros_like(l, dtype=torch.bool); mask[si[keep]] = True
        return torch.where(mask, l, torch.full_like(l, float("-inf")))
    def min_p(l, mp):
        probs = torch.softmax(l, -1)
        return torch.where(probs >= mp * probs.max(), l, torch.full_like(l, float("-inf")))
    hf = min_p(top_p(top_k(logits / T, K), P), MINP)           # temperature first
    lc = min_p(top_p(top_k(logits, K), P), MINP) / T          # temperature last
    from transformers.generation.logits_process import (LogitsProcessorList, TemperatureLogitsWarper,
                                                        TopKLogitsWarper, TopPLogitsWarper, MinPLogitsWarper)
    real = LogitsProcessorList([TemperatureLogitsWarper(T), TopKLogitsWarper(K), TopPLogitsWarper(P), MinPLogitsWarper(MINP)])
    hf_real = real(torch.zeros(1, 1, dtype=torch.long), logits[None].clone())[0]
    assert torch.equal(torch.isfinite(hf_real), torch.isfinite(hf)), "reimplementation disagrees with transformers"
    def summary(l):
        keep = torch.isfinite(l)
        probs = torch.softmax(l, -1)
        idx = probs.topk(int(keep.sum())).indices
        return {"kept": int(keep.sum()), "tokens": [{"text": piece(tok, int(i)), "p": round(float(probs[i]), 4)} for i in idx]}
    res = {"settings": {"temperature": T, "top_k": K, "top_p": P, "min_p": MINP},
           "transformers_order": summary(hf), "llama_cpp_order": summary(lc),
           "verified_against_transformers_warpers": True}
    base = torch.softmax(logits, -1)
    extra = torch.isfinite(lc) & ~torch.isfinite(hf)
    sweep = []
    for t in [0.5, 0.6, 0.7, 0.8, 0.9]:
        for mp in [0.02, 0.05, 0.1]:
            a_ = int(torch.isfinite(min_p(top_p(top_k(logits / t, K), P), mp)).sum())
            b_ = int(torch.isfinite(min_p(top_p(top_k(logits, K), P), mp)).sum())
            sweep.append({"temperature": t, "min_p": mp, "transformers": a_, "llama_cpp": b_})
    res["sweep"] = sweep
    res["llama_cpp_keeps_more_in"] = f"{sum(r['llama_cpp'] > r['transformers'] for r in sweep)} of {len(sweep)}"
    res["extra_tokens_mass_at_T1"] = round(float(base[extra].sum()), 4)
    lcp = torch.softmax(lc, -1)
    res["extra_tokens_mass_when_sampled"] = round(float(lcp[extra].sum()), 4)
    # how close the last kept token sits to the min-p cutoff, in the Transformers order
    hp = torch.softmax(logits / T, -1)
    res["min_p_margin"] = {"cutoff": round(float(MINP * hp.max()), 5), "last_kept": round(float(hp[torch.isfinite(hf)].min()), 5),
                           "first_dropped": round(float(hp[~torch.isfinite(hf)].max()), 5)}
    lk = torch.isfinite(lc)
    res["min_p_margin_llama_cpp"] = {"cutoff": round(float(MINP * base.max()), 5), "last_kept": round(float(base[lk].min()), 5),
                                     "first_dropped": round(float(base[~lk].max()), 5)}
    print(f"  T {T}, top_k {K}, top_p {P}, min_p {MINP}: Transformers keeps {res['transformers_order']['kept']} tokens, llama.cpp keeps {res['llama_cpp_order']['kept']}")
    save("samplers", {"meta": meta({"order_sources": "transformers generation/utils.py _get_logits_processor; llama.cpp common/common.h samplers (temperature last)"}), **res})

# ---- 10. fluent is not true -------------------------------------------------------------------------------
@torch.no_grad()
def truth():
    """Geometry-of-Truth cities (Marks and Tegmark 2023): "The city of X is in Y." in
    true and false versions. Score only the tokens that differ (the country), as
    log-probability, and count how often the true one is more likely."""
    import csv
    m, tok = model()
    rows = list(csv.DictReader(open(ROOT / "corpus/cities.csv")))
    by_city = {}
    for r in rows:
        by_city.setdefault(r["city"], {})["true" if r["label"] == "1" else "false"] = r
    pairs = [(v["true"], v["false"]) for v in by_city.values() if "true" in v and "false" in v]
    def country_lp(stmt, country):
        """Summed log-probability of the country's tokens, given everything before them."""
        prefix = stmt[: stmt.rindex(country)].rstrip()
        n = len(tok(prefix).input_ids)
        full = tok(prefix + " " + country, return_tensors="pt").input_ids.to(DEV)
        lp = torch.log_softmax(m(full).logits[0, :-1].float(), -1)
        return float(lp[torch.arange(n - 1, full.shape[1] - 1), full[0, n:]].sum())
    margins = []
    for t, f in pairs:
        margins.append(country_lp(t["statement"], t["country"]) - country_lp(f["statement"], f["country"]))
    wins = sum(x > 0 for x in margins)
    med = statistics.median(margins)
    print(f"  {len(pairs)} city pairs: true version more likely in {wins} ({wins / len(pairs):.1%}), median margin {med:.2f} nats")
    # the three hand pairs, scored the same way on the words that differ
    hand = [("The capital of France is", " Paris", " Berlin"), ("Water boils at sea level at", " 100", " 60"),
            ("The Go keyword that starts a goroutine is", " go", " async")]
    hand_rows = []
    for pre, a, b2 in hand:
        def lp(word):
            ids = tok(pre + word, return_tensors="pt").input_ids.to(DEV)
            n = len(tok(pre).input_ids)
            l = torch.log_softmax(m(ids).logits[0, :-1].float(), -1)
            return float(l[torch.arange(n - 1, ids.shape[1] - 1), ids[0, n:]].sum())
        la, lb = lp(a), lp(b2)
        hand_rows.append({"prefix": pre, "true": a.strip(), "false": b2.strip(), "p_true": round(math.exp(la), 4), "p_false": round(math.exp(lb), 5)})
        print(f"  {pre!r}: {a.strip()} {math.exp(la):.3f} vs {b2.strip()} {math.exp(lb):.4f}")
    # TruthfulQA (Lin et al. 2022): questions where the popular answer is wrong.
    # Best true answer vs best false answer, scored per answer token.
    tq = list(csv.DictReader(open(ROOT / "corpus/TruthfulQA.csv")))
    def ans_lp(q, a):
        prefix = f"Q: {q}\nA:"
        n = len(tok(prefix).input_ids)
        full = tok(prefix + " " + a, return_tensors="pt").input_ids.to(DEV)
        lp = torch.log_softmax(m(full).logits[0, :-1].float(), -1)
        return float(lp[torch.arange(n - 1, full.shape[1] - 1), full[0, n:]].mean())
    tq_rows = []
    for r in tq:
        t, f = ans_lp(r["Question"], r["Best Answer"]), ans_lp(r["Question"], r["Best Incorrect Answer"])
        tq_rows.append({"q": r["Question"], "cat": r["Category"], "true": r["Best Answer"], "false": r["Best Incorrect Answer"], "margin": round(t - f, 3)})
    tq_wins = sum(r["margin"] > 0 for r in tq_rows)
    print(f"  TruthfulQA: true answer more likely in {tq_wins} of {len(tq_rows)} ({tq_wins / len(tq_rows):.1%})")
    wrong_mis = sorted([r for r in tq_rows if r["cat"] == "Misconceptions" and r["margin"] < 0], key=lambda r: r["margin"])
    losers = sorted(zip(margins, pairs), key=lambda z: z[0])[:5]
    save("truth", {"meta": meta({"dataset": "geometry-of-truth cities.csv (Marks and Tegmark 2023)"}),
                   "pairs": len(pairs), "true_more_likely": wins, "share": round(wins / len(pairs), 4),
                   "median_margin_nats": round(med, 3), "margins_hist": [sum(lo <= x < lo + 2 for x in margins) for lo in range(-10, 20, 2)],
                   "hist_edges": list(range(-10, 22, 2)),
                   "worst": [{"true": p[0]["statement"], "false": p[1]["statement"], "margin": round(mg, 2)} for mg, p in losers],
                   "hand": hand_rows,
                   "truthfulqa": {"questions": len(tq_rows), "true_more_likely": tq_wins, "share": round(tq_wins / len(tq_rows), 4),
                                  "scoring": "mean log-probability per answer token, best true vs best false answer",
                                  "misconceptions_lost": wrong_mis[:12]}})


# ---- 11. the loop, token by token ---------------------------------------------------------------------
@torch.no_grad()
def loop():
    """Greedy generation one step at a time, recording the pick and where the
    end-of-text token stood at each step."""
    m, tok = model()
    prompt = "The invoice total is"
    ids = tok(prompt, return_tensors="pt").input_ids.to(DEV)
    eos = tok.eos_token_id
    steps = []
    for _ in range(40):
        logits = m(ids).logits[0, -1].float()
        probs = torch.softmax(logits, -1)
        pick = int(logits.argmax())
        steps.append({"text": piece(tok, pick), "id": pick, "p": round(float(probs[pick]), 4),
                      "eos_p": round(float(probs[eos]), 5), "eos_rank": int((probs > probs[eos]).sum()) + 1})
        if pick == eos:
            break
        ids = torch.cat([ids, torch.tensor([[pick]], device=DEV)], 1)
    print("  " + "".join(s["text"] for s in steps).replace("␣", " ")[:120])
    print(f"  end token: best rank {min(s['eos_rank'] for s in steps)}, max p {max(s['eos_p'] for s in steps)}")
    save("loop", {"meta": meta(), "prompt": prompt, "eos_id": eos, "eos_text": tok.decode([eos]), "steps": steps})


EXPERIMENTS = {
    "tokenizers": tokenizers,
    "distribution": distribution,
    "samples": samples,
    "context": context,
    "determinism": determinism,
    "kvcache": kvcache,
    "surprise": surprise, "samplers": samplers, "truth": truth,
    "arithmetic": arithmetic, "chat_template": chat_template, "loop": loop,
}
if __name__ == "__main__":
    chosen = sys.argv[1:] or list(EXPERIMENTS)
    for name in chosen:
        print(f"\n== {name}")
        EXPERIMENTS[name]()
    written = sorted(p.name for p in OUT.glob("*.json"))
    print(
        f"\n{len(chosen)} experiment(s) run; {len(written)} data file(s) in {OUT.relative_to(ROOT)}: {', '.join(written)}"
    )
    if not written:
        raise SystemExit("no data written")
