# agent/part1_without_harness.py — PART 1: the model with NO harness.
#
#   python3 agent/part1_without_harness.py gpt-3.5-turbo
#
# The model gets raw browser tools (open a URL, read the HTML, click or type by CSS selector)
# and a bare loop: ask the model -> do what it says -> repeat. Whatever it says at the end, we believe.
#
# Compared with part2_with_harness.py, nothing here helps it:
#   no [CONTEXT]     it must find the runbook and the policy by itself
#   no [TOOLS]       raw HTML and guessed CSS selectors
#   no [GUARDRAILS]  nothing stops a wrong or repeated refund
#   no [POLICY]      no second look before an irreversible click
#   no [EVALS]       we take its word for it
#   no [TOKEN SPEND] control: the full HTML is re-sent on every call

import json
from shared_setup import SYSTEM_PROMPT, USER_PROMPT, Browser, ask_model

TOOLS = [
    {"type": "function", "function": {"name": "open_url", "description": "Go to a URL.",
        "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
    {"type": "function", "function": {"name": "get_html", "description": "Get the HTML of the current page.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "click", "description": "Click the element matching a CSS selector.",
        "parameters": {"type": "object", "properties": {"selector": {"type": "string"}}, "required": ["selector"]}}},
    {"type": "function", "function": {"name": "fill", "description": "Type into the field matching a CSS selector.",
        "parameters": {"type": "object", "properties": {"selector": {"type": "string"}, "value": {"type": "string"}},
                       "required": ["selector", "value"]}}},
]


def run_raw_browser_tool(page, name, args):
    """Do exactly what the model asked. If it fails, hand back the raw error."""
    try:
        if name == "open_url":
            page.goto(args["url"])
        elif name == "get_html":
            page.evaluate("document.getElementById('narrator')?.remove()")   # never show the model our narration
            return page.content()[:12000]                                   # [TOKEN SPEND] ~12k characters, every time
        elif name == "click":
            page.click(args["selector"], timeout=3000)
        elif name == "fill":
            page.fill(args["selector"], args["value"], timeout=3000)
        return "ok"
    except Exception as e:
        return f"Error: {str(e).splitlines()[0]}"


def run_without_harness():
    with Browser("PART 1 · WITHOUT HARNESS") as browser:
        messages = [{"role": "system", "content": SYSTEM_PROMPT},     # the SAME prompts as Part 2
                    {"role": "user", "content": USER_PROMPT}]
        for step in range(20):                                       # only so a stuck run ends
            try:
                reply = ask_model(messages, TOOLS)
            except Exception as e:                                   # e.g. too much raw HTML for its memory
                browser.narrate(f"💥 the model crashed: {str(e)[:80]}", "bad")
                return browser.finish("(crashed)")
            messages.append(reply.model_dump(exclude_none=True))
            if not reply.tool_calls:                                 # it says it's done. We believe it.
                return browser.finish(reply.content)
            for call in reply.tool_calls:
                args = json.loads(call.function.arguments or "{}")
                result = run_raw_browser_tool(browser.page, call.function.name, args)
                failed = result.startswith("Error")
                browser.narrate(f"{'❌' if failed else '→'} {call.function.name}({json.dumps(args)[:60]})  "
                                f"{result[:40] if failed else ''}", "bad" if failed else "info")
                messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
        return browser.finish("(gave up after 20 steps)")


if __name__ == "__main__":
    run_without_harness()
