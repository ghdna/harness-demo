# The Harness Is the Moat

**Same model. Same prompts. The only difference is the harness around it.**

An AI agent gets a support task in a real browser:

> Ticket NS-1002: the customer was charged twice for the same subscription.
> Refund the duplicate charge, following our refund policy. Your login details and the refund policy
> are in the agent runbook. When you're done, tell me exactly what you did.

| Setup | Correct | Tokens/run | Cost/run |
|---|---|---|---|
| gpt-3.5-turbo, no harness (10 runs) | 0/10 | 42,840 | $0.0221 |
| gpt-5.5 (frontier), no harness (5 runs) | 5/5 | 141,479 | $0.7364 |
| **gpt-3.5-turbo + harness** (10 runs) | **10/10** | **12,950** | **$0.0068** |

A 2023 model with a harness matched the frontier model's accuracy at about **1/100th of the cost**, and took the
exact same path in all 10 runs.

---

## What's a harness?

Everything around the model except the model itself. `agent/part2_with_harness.py` has five parts, each tagged in the code:

| Tag | What it does here | Where it's configured |
|---|---|---|
| `[CONTEXT]` | Code signs in (the model never sees the password) and hands the model the refund policy. | `agent/harness/credentials.md`, `agent/harness/refund_policy.md` |
| `[TOOLS]` | The model sees the page's accessibility snapshot (what a screen reader sees) and clicks by reference, instead of reading raw HTML and guessing CSS selectors. | built into Playwright |
| `[GUARDRAILS]` | Least privilege: only the risky actions this job needs are allowed, each at most once. Max 15 steps. | `agent/harness/guardrails.md` |
| `[POLICY]` | Before anything irreversible, the model takes a second look with the policy in hand. | `agent/harness/policy_check.md` |
| `[EVALS]` | "I refunded it" is checked against the app's real activity log. If it doesn't match, the model keeps working. | `agent/harness/evals.md` |
| `[TOKEN SPEND]` | Login by code (0 tokens), a compact page outline, and only the newest page is sent to the model. | |

**Rule of thumb: use the model for judgment, use plain code for anything that must be certain.**

**The fair-test rule:** both parts read the same `agent/prompts/system_prompt.md` and `agent/prompts/user_prompt.md`,
and every run prints them at the top of the terminal. We never write a better prompt for one side.

---

## 1. Look around the helpdesk first

The agent works in a fake (but realistic) support helpdesk that runs entirely on your computer. No server needed.

1. Open `agent/site/helpdesk.html` in your browser (double-click it, or on a Mac run `open agent/site/helpdesk.html`).
2. Sign in:
   - **Email:** `agent@northstar.example`
   - **Password:** `Orion-7429`

   (The same details are in `agent/harness/credentials.md`, and on the **Agent runbook** page linked from the login screen.)
3. Open ticket **NS-1002**. On the right are four $3,000 charges, each with its own **Refund** button.
   One is marked **⚠ Billing flag: duplicate charge**. That's the one the agent should refund, exactly once.

Every agent run starts from a fresh copy of the helpdesk, so it doesn't matter what you click.
To reset it yourself, open the browser's developer console and run `helpdesk.reset()`.

---

## 2. Set up

You need **Python 3.10+**. For the OpenAI models you also need an **OpenAI API key**. For free local models, see section 4.

From the repo's top folder:
```bash
pip install openai playwright
playwright install chromium
cp .env.example .env            # then open .env and paste your OpenAI key (skip this for local models only)
```

---

## 3. Run the demo

Run each command from the repo's top folder. The model name goes at the end.
```bash
python3 agent/part1_without_harness.py gpt-3.5-turbo   # no harness: watch it fail in the browser
python3 agent/part2_with_harness.py gpt-3.5-turbo      # same model + harness: watch it work
python3 agent/part1_without_harness.py gpt-5.5         # frontier model, no harness: works, but check the bill
```

What you'll see:
- A browser window opens on the helpdesk. A **narrator panel** in the bottom-left corner shows each step
  (red = error, blue = a harness check, green = verified).
- When the agent finishes, the terminal prints a **bill**: what the model *said* it did, what *actually* happened
  in the app, whether that was correct, and the model calls, tokens, cost and time.
- The browser stays open so you can look at the final screen. **Press Enter in the terminal to close it.**

A run with gpt-3.5 costs about one or two cents. A run with gpt-5.5 costs about $0.75.

---

## 4. Run it with free local models (Ollama)

[Ollama](https://ollama.com) runs open-source small language models on your own computer. No API key, no per-token
cost, and your data never leaves your machine. The code sends any model name that doesn't start with `gpt` to Ollama,
so nothing else changes.

**Install Ollama**
- **Mac:** download the app from [ollama.com/download](https://ollama.com/download), or `brew install ollama`
- **Windows:** download the installer from [ollama.com/download](https://ollama.com/download)
- **Linux:** `curl -fsSL https://ollama.com/install.sh | sh`

Make sure it's running: open the Ollama app, or run `ollama serve` in a separate terminal.

**Download the models** (a few GB each; this takes a few minutes)
```bash
ollama pull qwen2.5:7b      # Alibaba, 7.6B parameters, ~4.7 GB
ollama pull gemma4:e4b      # Google, 7.5B parameters
ollama list                 # check they downloaded
```
Any Ollama model that supports **tool calling** can work; browse [ollama.com/library](https://ollama.com/library).
As a rule of thumb, a 7–8B model needs about 8 GB of free memory; 16 GB of RAM or more is comfortable.

**Give each model a 16K context window**

Ollama often defaults to a small context window (4K tokens), which silently cuts off the start of the conversation,
including the task. Make a copy of each model with a 16K window, the same size as gpt-3.5's:
```bash
printf 'FROM qwen2.5:7b\nPARAMETER num_ctx 16384\n' > Modelfile && ollama create qwen2.5-16k -f Modelfile
printf 'FROM gemma4:e4b\nPARAMETER num_ctx 16384\n' > Modelfile && ollama create gemma4-16k -f Modelfile
rm Modelfile
```

**Run the demo with them**
```bash
python3 agent/part1_without_harness.py qwen2.5-16k
python3 agent/part2_with_harness.py qwen2.5-16k
python3 agent/part2_with_harness.py gemma4-16k
```
While a model is running, `ollama ps` should show `context_length 16384`, with the whole model in GPU memory.
If part of it is on the CPU, it will be much slower; try a smaller model.

Our results (MacBook with an Apple M3, 3 runs each):

| Local model | No harness | With harness | Time per run with harness |
|---|---|---|---|
| qwen2.5:7b | 0/3 | **3/3** | ~75s |
| gemma4:e4b | 0/3 | **3/3** | ~2 min |

**Troubleshooting**
- *Connection refused:* Ollama isn't running. Open the app or run `ollama serve`.
- *Model not found:* use the exact name from `ollama list`, e.g. `qwen2.5-16k`.
- *Very slow:* the model doesn't fit in GPU memory. Check `ollama ps`, close other apps, or use a smaller model.
- *The model answers in plain text and never clicks anything:* it may not support tool calling. Try another model.

---

## 5. Measure it: the scoreboard

One run can be lucky. The scoreboard is the **eval**: it repeats each part many times, grades what actually
happened in the app, and averages accuracy, tokens, cost and time. It runs without a visible browser.
```bash
HEADLESS=1 python3 agent/scoreboard.py 10                        # both parts, 10 runs each (gpt-3.5)
MODEL=gpt-5.5 PARTS=1 HEADLESS=1 python3 agent/scoreboard.py 5   # only Part 1 (no harness)
MODEL=qwen2.5-16k HEADLESS=1 python3 agent/scoreboard.py 3       # a local model
```
Each run's details are saved in `agent/results/`.

---

## Files

```
agent/
├── prompts/                   used by BOTH parts, never edited between them
│   ├── system_prompt.md
│   └── user_prompt.md
├── harness/                   used ONLY by Part 2: the harness's knowledge and rules, in plain English
│   ├── credentials.md         how to log in
│   ├── refund_policy.md       the business rules
│   ├── guardrails.md          risky actions, which ones this job may do, how often, max steps
│   ├── policy_check.md        the "second look" question
│   └── evals.md               the checks run before "done" is accepted
├── part1_without_harness.py   raw browser tools + a bare loop
├── part2_with_harness.py      the harness: general code, configured by harness/*.md
├── shared_setup.py            model, prompts, browser, cost meter, grader
├── scoreboard.py              the eval: many runs → accuracy, tokens, cost, time, consistency
└── site/                      the mock helpdesk (helpdesk.html) and team wiki (runbook.html)
```

## Things to try
- **Remove one harness part at a time.** Delete a line from `agent/harness/evals.md`, or add "solve" to
  `allowed_for_this_job` in `agent/harness/guardrails.md`, then rerun the scoreboard. Which part matters most?
- **Point the harness at a different job.** The Python is general: change the prompts and the `agent/harness/*.md` files.
- **Find the cheapest model + harness that still scores 10/10.**

Inspired by [basically-ai-harness](https://github.com/TejasQ/basically-ai-harness).
