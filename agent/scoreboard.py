# agent/scoreboard.py — [EVALS] Run each part many times and score them. Also measures [TOKEN SPEND].
#
#   HEADLESS=1 python3 agent/scoreboard.py 10                        # both parts, 10 runs each
#   MODEL=gpt-5.5 PARTS=1 HEADLESS=1 python3 agent/scoreboard.py 5   # only Part 1 (no harness)
#   MODEL=qwen2.5-16k HEADLESS=1 python3 agent/scoreboard.py 3       # a local model
#
# One run can be lucky. Ten runs tell you how reliable something is, what it costs, and
# whether it does the same thing every time. Grading uses what ACTUALLY happened in the app.

import io, json, os, sys, time, contextlib, pathlib
import part1_without_harness, part2_with_harness
from shared_setup import MODEL, USAGE, cost_in_dollars, is_refund_correct


def run_many_times(run_function, times):
    runs = []
    for i in range(times):
        with contextlib.redirect_stdout(io.StringIO()):      # keep the screen tidy
            try:
                answer, log = run_function()
            except Exception as e:                            # a crash counts as a failed run
                answer, log = f"crashed: {e}", []
                USAGE["end"] = time.time()
        run = {"correct": is_refund_correct(log), "log": log, "said": (answer or "")[:160],
               "seconds": round(USAGE["end"] - USAGE["start"]), "model_calls": USAGE["calls"],
               "tokens": USAGE["in"] + USAGE["out"], "cost": cost_in_dollars()}
        runs.append(run)
        print(f"  run {i + 1}: {'PASS' if run['correct'] else 'FAIL'}  {run['tokens']:>7,} tokens  "
              f"{run['seconds']:>3}s   actually happened: {log or 'nothing'}")
    return runs


def summarize_runs(label, runs):
    n = len(runs)
    wins = sum(r["correct"] for r in runs)
    average = lambda key: sum(r[key] for r in runs) / n
    spend = sum(r["cost"] for r in runs)
    cost_per_correct = f"${spend / wins:.4f}" if wins else "never correct"
    different_outcomes = len({json.dumps(r["log"]) for r in runs})
    return (f"{label:<12} {wins}/{n} correct | {average('model_calls'):.1f} model calls | "
            f"{average('tokens'):,.0f} tokens | ${average('cost'):.4f} per run | "
            f"cost per correct result: {cost_per_correct} | {average('seconds'):.0f}s | "
            f"{different_outcomes} different outcome(s)")


if __name__ == "__main__":
    times = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    parts = os.environ.get("PARTS", "12")
    print(f"model: {MODEL}")
    without, with_harness = [], []
    if "1" in parts:
        print("\nPART 1 — without harness")
        without = run_many_times(part1_without_harness.run_without_harness, times)
    if "2" in parts:
        print("\nPART 2 — with harness")
        with_harness = run_many_times(part2_with_harness.run_with_harness, times)

    print(f"\n==================== {MODEL} ====================")
    if without:
        print(summarize_runs("No harness", without))
    if with_harness:
        print(summarize_runs("Harness", with_harness))

    folder = pathlib.Path(__file__).parent / "results"
    folder.mkdir(exist_ok=True)
    (folder / f"{MODEL.replace(':', '_')}.json").write_text(
        json.dumps({"model": MODEL, "without_harness": without, "with_harness": with_harness}, indent=1))
