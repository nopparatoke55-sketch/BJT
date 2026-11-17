# Lab 03 — Browser Acceptance Record (A1–A5)

> Fill the **expected** column from your own hand calculation (Engineering
> Electronics) *before* running the browser cases. Do not copy values from the
> program being tested. Fill **observed**, **method** and **status** only after
> actually running each case in a browser.

## Shared inputs

| Quantity | Value |
|---|---|
| V_CC | 12 V |
| R_C | 2.2 kΩ (enter `2.2`) |
| β | 100 |
| V_BE | 0.70 V |

Form units are **kΩ and volts**. The app multiplies every resistor field by
1000 exactly once before calling the Python math, so the internal calculation
still runs in ohms. Convert the lab table to the form as follows:

- 1 kΩ = `1`
- 2.2 kΩ = `2.2`
- 22 kΩ = `22`
- 100 kΩ = `100`
- 1 MΩ = `1000`

## Tolerance

Compare against the unrounded hand calculation:

- I_C: ±0.01 mA
- V_CE: ±0.02 V

## Cases

| Case | Mode and inputs | Expected (hand calc) | Observed (page) | Method | Status |
|---|---|---|---|---|---|
| A1 · original mode | Divider · R1 = 100 kΩ, R2 = 22 kΩ, RE = 1 kΩ | I_C = ___ mA · V_CE = ___ V | — | — | — |
| A2 · Fixed | Fixed · RB = 1 MΩ (enter `1000`) | I_C = ___ mA · V_CE = ___ V (no RE field needed) | — | — | — |
| A3 · Emitter | Emitter · RB = 1 MΩ (enter `1000`), RE = 1 kΩ (enter `1`) | I_C = ___ mA · V_CE = ___ V | — | — | — |
| A4 · single change | Emitter · same as A3 but RE = 2 kΩ (enter `2`) | Prediction: I_C will ☐ increase ☐ decrease because ________ · I_C = ___ mA · V_CE = ___ V | — | — | — |
| A5 · invalid input | Fixed · RB = 0 | Field message for RB; page does not crash and shows no result from a previous round | — | — | — |

**Method** must name what was actually used: `Playwright MCP`, `OpenCode Browser`,
or `Manual`. Mark `PASS`, `FAIL`, or `NOT RUN` (with the blocker) in **Status**.

## Evidence

Attach at least one piece of evidence from the browser per submission, e.g. the
visible result text copied from the page or a screenshot.

## Notes

- A1 must match the Lab 02 result with the same physical inputs. If Lab 02 did
  not match the independent reference, record the difference and consult the TA.
- A5: the message may come from the form or from Flask; state which one, and
  confirm that Flask also rejects the input (client-side `required` alone is not
  proof).
- After any code fix, record before/after results and re-run the affected cases.
