# calibration-log — β+ audit-calibration records for WARN-first gates

Append-only log of CAL-EMIT[] records emitted by chain-evaluator when §2i/§2j/§2d-severity gates fire (path β+ audit-monitored calibration, per directives.md).

Each record is appended by chain-evaluator when a gate fires WARN. DA appends verdict at r2 exit-gate. audit-calibration-gate.py reads this file to evaluate PROMOTE/RECALIBRATE/CALIBRATING thresholds.

## Format

Each record is a single line ending in `|da-verdict:{legitimate|false-positive|not-reviewed}` (or `PENDING` before DA verdicts it):

```
