# Evals

When the model says it's done, plain code runs these checks against the app's activity log.
If a check fails, the model gets the message and keeps working. Delete a line to switch that check off.

- claims_match_the_app: You said you did '{action}', but the app shows no {action}.
- something_changed: Nothing has changed in the app yet.
- summary_written: Write a short summary of exactly what you did.
