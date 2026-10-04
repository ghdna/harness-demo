# agent/part2_with_harness.py — PART 2: the SAME model and the SAME prompts, wrapped in a harness.
#
#   python3 agent/part2_with_harness.py gpt-3.5-turbo
#
# A harness is everything around the model except the model itself. Ours has five parts:
#
#   1. [CONTEXT]     the right information: plain markdown files in agent/harness/
#   2. [TOOLS]       a readable page and simple buttons, instead of raw HTML and CSS selectors
#   3. [GUARDRAILS]  hard limits the model cannot talk its way past
#   4. [POLICY]      a second look before anything that can't be undone
#   5. [EVALS]       check what the model claims against what really happened, and loop until true
#
# [TOKEN SPEND] marks each place the harness saves tokens (= money and time).
#
# The code is general: it works on any web app with a login form and buttons. Everything specific to
# this job lives in the markdown files. Nothing here knows which charge to refund; the model decides that.
# Rule of thumb: use the model for judgment, use plain code for anything that must be certain.

import json
from shared_setup import SYSTEM_PROMPT, USER_PROMPT, Browser, ask_model, read_md, read_settings

# ═══ 1. [CONTEXT] the right information, from markdown files ═══════════════════

CREDENTIALS = read_settings("harness/credentials.md")
POLICY = read_md("harness/refund_policy.md")
GUARDRAILS = read_settings("harness/guardrails.md")
POLICY_CHECK = read_md("harness/policy_check.md")      # the "second look" question asked before risky clicks
EVALS = read_settings("harness/evals.md")


def sign_in(browser):
    """Logging in isn't a judgment call, so plain code does it, on any standard login form.
    [TOKEN SPEND] 0 tokens, and the password never goes into a prompt."""
    browser.page.fill("input[type=email]", CREDENTIALS["email"])
    browser.page.fill("input[type=password]", CREDENTIALS["password"])
    browser.page.press("input[type=password]", "Enter")
    browser.narrate("🛡 CONTEXT: signed in with code from credentials.md · 0 tokens · model never sees the password",
                    "harness")


# ═══ 2. [TOOLS] a readable page and simple buttons ══════════════════════════════
# The model sees the page's accessibility snapshot (the outline a screen reader uses, built into Playwright):
#     - cell "CH-4418 Aug 1 · Pro subscription · August ⚠ Billing flag: duplicate charge"
#     - button "Refund" [ref=e97]
# and acts with click("e97"). The same approach Microsoft's Playwright MCP server uses for AI agents.

TOOLS = [
    {"type": "function", "function": {"name": "click", "description": "Click the element with this ref, e.g. e97.",
        "parameters": {"type": "object", "properties": {"ref": {"type": "string"}}, "required": ["ref"]}}},
    {"type": "function", "function": {"name": "type_text", "description": "Type text into the field with this ref.",
        "parameters": {"type": "object", "properties": {"ref": {"type": "string"}, "text": {"type": "string"}},
                       "required": ["ref", "text"]}}},
]
PAGE_HEADER = "THE PAGE NOW"


def show_page(browser):
    """What the model sees after every action: what really happened so far, and the page.
    [TOKEN SPEND] only the page's <main> content, as a compact outline, not ~12k characters of raw HTML."""
    browser.page.wait_for_timeout(300)
    main = browser.page.locator("main")
    browser.snapshot = (main if main.count() else browser.page.locator("body")).aria_snapshot(mode="ai")
    return f"{PAGE_HEADER} (act on elements by their ref).\nDone so far: {browser.activity_log()}\n\n{browser.snapshot}"


def describe(browser, ref):
    """The element's label, and the text of the row it sits in (WHICH charge is this Refund button for?).
    Returns (None, None) if the ref isn't on the page the model just saw."""
    if f"[ref={ref}]" not in browser.snapshot:
        return None, None
    try:
        label, row = browser.page.locator(f"aria-ref={ref}").evaluate(
            "e => [(e.innerText || e.placeholder || '').trim(),"
            "      (e.closest('tr, li, article, section') || e.parentElement).innerText]", timeout=3000)
    except Exception:
        return None, None
    return label, " ".join(row.split())


# ═══ 3. [GUARDRAILS] hard limits ═══════════════════════════════════════════════

MAX_STEPS = int(GUARDRAILS["max_steps"])                      # [TOKEN SPEND] also caps the bill
RISKY_ACTIONS = GUARDRAILS["risky_actions"].split(", ")       # anything that changes the ticket or moves money
ALLOWED = GUARDRAILS["allowed_for_this_job"].split(", ")      # least privilege: only what this job needs
MAX_TIMES = int(GUARDRAILS["max_times_each"])


def risky_action(text):
    """Which risky action from guardrails.md does this text mention? ('solve' also matches 'Solved'.)"""
    return next((action for action in RISKY_ACTIONS if action.rstrip("e") in text.lower()), None)


def guardrail_blocks(browser, action):
    """Plain-code limits: is this action allowed for this job, and has it already been done enough times?"""
    if action not in ALLOWED:
        return f"'{action}' is not allowed for this job"
    if sum(risky_action(entry) == action for entry in browser.activity_log()) >= MAX_TIMES:
        return f"'{action}' is allowed only {MAX_TIMES} time(s)"
    return None


# ═══ 4. [POLICY] a second look before anything irreversible ═════════════════════

def policy_allows(target):
    """Ask the same model, with fresh eyes, the question in policy_check.md."""
    question = POLICY_CHECK.format(policy=POLICY, target=target)
    answer = ask_model([{"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": USER_PROMPT},
                        {"role": "user", "content": question}]).content or ""
    return "VERDICT: YES" in answer.upper(), answer


# ═══ 5. [EVALS] don't trust "I did it", check it ═══════════════════════════════

def problems_with(answer, log):
    """Run every check listed in evals.md. Each failure becomes feedback for the model."""
    answer = answer or ""
    claimed = [action for action in RISKY_ACTIONS if action.rstrip("e") in answer.lower()]
    failures = {                                       # check name -> one entry per failure
        "claims_match_the_app": [{"action": a} for a in claimed if not any(risky_action(e) == a for e in log)],
        "something_changed": [{}] if len(log) <= 1 else [],          # nothing but the login
        "summary_written": [{}] if len(answer.split()) < 5 else [],
    }
    return [message.format(**failure) for check, message in EVALS.items() for failure in failures[check]]


# ═══ THE LOOP: the model decides, the harness acts and checks ═══════════════════

def act(browser, name, args):
    """Carry out one model action, through the guardrails and the policy. Mistakes become feedback, not crashes."""
    ref = str(args.get("ref"))
    label, row = describe(browser, ref)
    if label is None:
        return f"There is no element '{ref}' on the page. Use a ref from the page."
    target = f'"{label}" in: {row}'
    action = risky_action(label)
    if name == "click" and action:
        blocked = guardrail_blocks(browser, action)
        if blocked:
            browser.narrate(f"🛡 GUARDRAILS: blocked, {blocked}", "harness")
            return f"Blocked: {blocked}."
        allowed, why = policy_allows(target)
        browser.narrate(f"🛡 POLICY: {'approved' if allowed else 'BLOCKED'} {target[:85]}", "harness" if allowed else "bad")
        if not allowed:
            return f"Blocked by the policy check: {why}"
    try:
        element = browser.page.locator(f"aria-ref={ref}")
        element.fill(args.get("text", "")) if name == "type_text" else element.click()
    except Exception as e:
        return f"That didn't work: {str(e).splitlines()[0][:100]}"
    browser.narrate(f"→ {name} {target[:95]}")
    return f"Done: {name} {target}"


def run_with_harness():
    with Browser("PART 2 · WITH HARNESS") as browser:
        sign_in(browser)
        messages = [{"role": "system", "content": SYSTEM_PROMPT},             # the SAME prompts as Part 1
                    {"role": "user", "content": USER_PROMPT},
                    {"role": "user", "content": f"{POLICY}\n\nYou are signed in."}]   # harness-added context
        for step in range(MAX_STEPS):
            # [CONTEXT] + [TOKEN SPEND] the model sees only the newest page; older pages are dropped
            messages = [m for m in messages if not str(m.get("content")).startswith(PAGE_HEADER)]
            messages.append({"role": "user", "content": show_page(browser)})
            reply = ask_model(messages, TOOLS)
            messages.append(reply.model_dump(exclude_none=True))
            if reply.tool_calls:
                for call in reply.tool_calls:
                    result = act(browser, call.function.name, json.loads(call.function.arguments or "{}"))
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
                continue
            problems = problems_with(reply.content, browser.activity_log())     # it says it's done -> [EVALS]
            if not problems:
                browser.narrate("✅ EVALS: the app confirms what the model claims", "good")
                return browser.finish(reply.content)
            browser.narrate(f"🛡 EVALS: rejected: {problems[0]}", "harness")
            messages.append({"role": "user", "content": "Not done yet:\n- " + "\n- ".join(problems)})
        browser.narrate(f"🛡 GUARDRAILS: stopped after {MAX_STEPS} steps", "harness")
        return browser.finish(f"(stopped after {MAX_STEPS} steps)")


if __name__ == "__main__":
    run_with_harness()
