# agent/shared_setup.py — what BOTH parts share: the model, the prompts, the browser, the bill, the grader.

import os, re, sys, time, pathlib
from openai import OpenAI
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).parent
HEADLESS = os.environ.get("HEADLESS") == "1"           # the scoreboard runs without a visible browser


def read_md(path):
    return (HERE / path).read_text().strip()


def read_settings(path):
    """Read '- key: value' lines from a markdown file into a dict."""
    return dict(re.findall(r"^- (\w+): (.+)$", read_md(path), re.M))


# ── the model ── pick it on the command line: python3 agent/part1_without_harness.py gpt-5.5
MODEL = next((a for a in sys.argv[1:] if not a.isdigit()), os.environ.get("MODEL", "gpt-3.5-turbo"))

env_file = HERE.parent / ".env"                         # holds OPENAI_API_KEY
for line in env_file.read_text().splitlines() if env_file.exists() else []:
    if "=" in line and not line.startswith("#"):
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))

client = (OpenAI() if MODEL.startswith("gpt")                                  # OpenAI
          else OpenAI(base_url="http://localhost:11434/v1", api_key="ollama"))  # or Ollama, on your laptop

# ── the prompts ── identical for both parts, never edited. They live in agent/prompts/.
HELPDESK_URL = (HERE / "site" / "helpdesk.html").as_uri()
SYSTEM_PROMPT = read_md("prompts/system_prompt.md")
USER_PROMPT = read_md("prompts/user_prompt.md").replace("{helpdesk_url}", HELPDESK_URL)

# ── the meter ── [TOKEN SPEND] you can't optimize what you don't measure.
PRICES = {"gpt-3.5-turbo": (0.50, 1.50), "gpt-5.5": (5.00, 30.00)}   # $ per 1M tokens in/out (OpenAI, Oct 2026)
USAGE = {}


def ask_model(messages, tools=None):
    reply = client.chat.completions.create(model=MODEL, messages=messages, **({"tools": tools} if tools else {}))
    USAGE["calls"] += 1
    USAGE["in"] += reply.usage.prompt_tokens
    USAGE["out"] += reply.usage.completion_tokens
    return reply.choices[0].message


def cost_in_dollars():
    price_in, price_out = PRICES.get(MODEL, (0, 0))
    return (USAGE["in"] * price_in + USAGE["out"] * price_out) / 1e6


def is_refund_correct(log):
    """[EVALS] The grader: exactly one refund, of the charge Billing flagged (CH-4418). The harness never sees this."""
    return [entry for entry in log if entry.startswith("refund")] == ["refund CH-4418"]


# ── the browser ── a real Chrome window on a freshly reset helpdesk, with a narrator panel on screen.
NARRATOR_JS = """lines => {
  let box = document.getElementById('narrator');
  if (!box) {
    box = Object.assign(document.createElement('div'), {id: 'narrator'});
    box.setAttribute('aria-hidden', 'true');                     // hidden from the model's page view
    box.style.cssText = 'position:fixed;bottom:16px;left:16px;width:540px;z-index:99999;padding:12px 14px;' +
      'font:13px/1.5 Menlo,monospace;background:#111827ee;border-radius:10px;box-shadow:0 8px 30px #0006';
    document.body.appendChild(box);
  }
  box.innerHTML = lines.map(([text, color]) => `<div style="color:${color}"></div>`).join('');
  box.querySelectorAll('div').forEach((row, i) => row.textContent = lines[i][0]);
}"""
COLORS = {"info": "#e5e7eb", "bad": "#f87171", "harness": "#93c5fd", "good": "#4ade80"}


class Browser:
    def __init__(self, title):
        self.title, self.lines = title, []

    def __enter__(self):
        print(f"\n═══ {self.title} · model: {MODEL}\nSYSTEM PROMPT: {SYSTEM_PROMPT}\n"
              f"USER PROMPT:   {' '.join(USER_PROMPT.replace(HELPDESK_URL, 'helpdesk.html').split())}\n═══")
        self.playwright = sync_playwright().start()
        self.chrome = self.playwright.chromium.launch(headless=HEADLESS, slow_mo=0 if HEADLESS else 250)
        self.page = self.chrome.new_page(viewport={"width": 1280, "height": 800})
        self.page.goto(HELPDESK_URL)
        self.page.evaluate("helpdesk.reset()")
        USAGE.update({"calls": 0, "in": 0, "out": 0, "start": time.time()})
        self.narrate(f"{self.title} · {MODEL}")
        return self

    def narrate(self, text, kind="info"):
        """Show what's happening, in the terminal and on screen."""
        print(f"  {text}")
        self.lines = (self.lines + [(text[:110], COLORS[kind])])[-7:]
        if not HEADLESS:
            try:
                self.page.evaluate(NARRATOR_JS, self.lines)
                self.page.wait_for_timeout(700)
            except Exception:
                pass                                              # the page was mid-navigation; skip this frame

    def activity_log(self):
        """The SYSTEM OF RECORD: what really happened in the app. (In real life: your database or audit API.)"""
        try:
            return self.page.evaluate("JSON.parse(localStorage.getItem('nh') || '{}').log || []")
        except Exception:
            return []

    def finish(self, answer):
        """Print the bill and return the result."""
        USAGE["end"] = time.time()
        log = self.activity_log()
        price = f"${cost_in_dollars():.4f}" if MODEL in PRICES else "$0 (runs on your laptop)"
        print(f"""
┌─ {self.title} · {MODEL}
│  Model says:        {' '.join((answer or '').split())[:200]}
│  Actually happened: {log or 'nothing'}
│  Result:            {'✅ CORRECT' if is_refund_correct(log) else '❌ WRONG'}
│  Model calls:       {USAGE['calls']}
│  Tokens:            {USAGE['in'] + USAGE['out']:,}  ({USAGE['in']:,} in / {USAGE['out']:,} out)
│  Cost:              {price}
│  Time:              {USAGE['end'] - USAGE['start']:.0f}s
└──────────────────────────────────────────────""")
        return answer, log

    def __exit__(self, *error):
        if not HEADLESS:
            input("\nPress Enter to close the browser...")
        self.chrome.close()
        self.playwright.stop()
