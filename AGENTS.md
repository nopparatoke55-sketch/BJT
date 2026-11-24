# AGENTS.md — Engineering & AI rules for this repository

This project is an ENG29 2121 teaching app. Correctness and provenance matter
more than visual polish.

## 1. Preserve the Lab 03 contract

- Do **not** remove or rewrite the three analytical DC-bias modes in `bjt.py`
  (Voltage Divider, Fixed, Emitter).
- Keep the existing Lab 03 routes (`GET /`, `POST /calculate`) and tests
  working. Lab 04 extends them; it does not replace them.
- Keep `bjt.py` free of Flask and SPICE imports.
- Keep engineering formulas out of `app.py` and out of templates.

## 2. Never fabricate simulation data

- Every SPICE value shown in the UI must come from parsing the output files
  written by the ngspice process for that request.
- Never hard-code a trace, a “success” value, or a placeholder plot.
- Never show a previous plot together with a new `Success` status.
- If ngspice is missing, exits non-zero, times out, writes an empty file, or
  returns unparsable data, surface `SpiceUnavailable` / `SpiceError` with the
  netlist and log.
- If a cutoff frequency is outside the swept range, say
  “not determined in sweep range”; do not invent it.

## 3. Keep provenance visible

- Label SPICE output as `ngspice` with the detected version and model name.
- Keep analytical reference values in a separate column/section.
- Explain that SPICE and analytical values use different models and are not
  expected to match every digit.
- Keep the generated netlist and ngspice log reachable from the page.

## 4. Input safety

- Validate every form value on the server before building a netlist.
- Convert units exactly once: kΩ → Ω, µF → F, mV → V.
- Reject non-numeric, non-finite, out-of-range and zero-denominator values with
  a field-level message; never answer HTTP 500 for user input.
- Call external programs with `subprocess.run([...])`, no `shell=True`, a
  timeout and an isolated working directory.

## 5. UI rules

- Engineering readability first: values, units, mode and run status must be
  legible on desktop and mobile.
- Do not hide errors behind decoration. Do not require fields that the selected
  analysis does not use.
- Keep the Lab 03 sections intact while adding Lab 04 content.
- `static/app.js` is progressive enhancement only; the form must still work
  with JavaScript disabled.

## 6. Tests and acceptance

- Run `pytest` from the repository root with the project virtual environment.
- New solver/parser logic needs tests that do not depend on a live ngspice
  binary; real-run evidence belongs in `docs/validation.md`.
- Record `PASS`, `FAIL` or `NOT RUN` honestly. A tool that did not execute is
  `NOT RUN`, never `PASS`.
- After a code fix, re-run the affected tests and update the validation record.

## 7. Scope

In scope: one reference CE voltage-divider circuit, real `.op` / `.ac` /
`.tran`, analytical comparison, UI/provenance and browser acceptance.

Out of scope for this lab: free-form circuit editing, AC analysis for every
bias mode, FETs, a custom SPICE solver, animated current overlays, and public
deployment.
