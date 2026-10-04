# Guardrails

Hard limits the model cannot talk its way past. Plain code enforces them.
Risky actions are anything that changes the ticket or moves money. Only the ones this job needs are allowed.

- max_steps: 15
- risky_actions: refund, solve, pending, escalate, merge, assign, delete
- allowed_for_this_job: refund
- max_times_each: 1
