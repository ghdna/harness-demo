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

### The fair-test rule
Both parts read the same `agent/prompts/system_prompt.md` and `agent/prompts/user_prompt.md`, and every run prints them at the top
of the terminal. We never write a better prompt for one side.

## Try it
```bash
pip install openai playwright
playwright install chromium
cp .env.example .env            # add your OpenAI key (not needed if you only use local models)

python3 agent/part1_without_harness.py gpt-3.5-turbo   # watch it fail in the browser
python3 agent/part2_with_harness.py gpt-3.5-turbo      # same model + harness: watch it work
python3 agent/part1_without_harness.py gpt-5.5         # frontier model, no harness: works, but check the bill
```
Each run opens a real browser with a narrator in the corner (red = error, blue = harness, green = verified) and ends
with a bill: what the model said, what actually happened, tokens, cost and time. Press Enter to close the browser.

## Run it with local models (free, via Ollama)

[Ollama](https://ollama.com) runs open-source small language models on your own computer. No API key and no
per-token cost, and your data never leaves your machine. The code sends any model name that doesn't start
with `gpt` to Ollama, so nothing else changes.

**1. Install Ollama**
- **Mac:** download the app from [ollama.com/download](https://ollama.com/download), or `brew install ollama`
- **Windows:** download the installer from [ollama.com/download](https://ollama.com/download)
- **Linux:** `curl -fsSL https://ollama.com/install.sh | sh`

Then make sure it's running: open the Ollama app, or run `ollama serve` in a separate terminal.
It listens on `http://localhost:11434`.

**2. Download the models** (each is a few GB; this takes a few minutes)
```bash
ollama pull qwen2.5:7b      # Alibaba, 7.6B parameters, ~4.7 GB
ollama pull gemma4:e4b      # Google, 7.5B parameters
ollama list                 # check they downloaded
```
Any Ollama model that supports **tool calling** can work. Browse [ollama.com/library](https://ollama.com/library).
As a rule of thumb, a 7–8B model needs about 8 GB of free memory; 16 GB of RAM or more is comfortable.

**3. Give each model a 16K context window**

Ollama often defaults to a small context window (4K tokens), which silently cuts off the start of the conversation,
including the task. Make a copy of each model with a 16K window, the same size as gpt-3.5's, so the comparison is fair:
```bash
printf 'FROM qwen2.5:7b\nPARAMETER num_ctx 16384\n' > Modelfile && ollama create qwen2.5-16k -f Modelfile
printf 'FROM gemma4:e4b\nPARAMETER num_ctx 16384\n' > Modelfile && ollama create gemma4-16k -f Modelfile
rm Modelfile
```

**4. Run the demo**
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

## Measure it: the scoreboard
One run can be lucky. The scoreboard is the eval: it repeats each part and averages the results.
Each run's details are saved in `agent/results/`.
```bash
HEADLESS=1 python3 agent/scoreboard.py 10                        # both parts, 10 runs each
MODEL=gpt-5.5 PARTS=1 HEADLESS=1 python3 agent/scoreboard.py 5   # one part only
MODEL=qwen2.5-16k HEADLESS=1 python3 agent/scoreboard.py 3       # a local model
```

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
