# Lab 04 — CE Amplifier SPICE Integration Plan

> Short integration plan required before coding by the Lab 04 handout.
> This plan extends the existing Lab 03 project; it does not recreate it.

## Goal

Add real ngspice DC (`.op`), AC (`.ac`) and transient (`.tran`) runs for one
reference **CE voltage-divider** circuit, expose the results with units and
provenance, and keep every Lab 03 analytical DC-bias mode working.

## Reused files (must not be removed or rewritten)

| File | Reused as |
|---|---|
| `bjt.py` | Lab 03 analytical DC bias (Fixed, Emitter, Divider) — unchanged |
| `app.py` | Existing routes and Lab 03 form/result rendering — extended only |
| `templates/index.html` | Existing three-column Lab 03 UI — extended with a simulation section |
| `static/style.css` | Existing Lab 03 styling — extended with simulation classes |
| `tests/test_bjt.py`, `tests/test_app.py` | Lab 03 regression suite — must keep passing |
| `docs/validation.md` | Lab 03 A1–A5 record — extended with Lab 04 B1–B8 |

## New files

| File | Purpose |
|---|---|
| `spice_engine.py` | Validate simulation inputs, generate netlist, run `ngspice` via `subprocess`, parse ASCII `wrdata` output, raise explicit errors |
| `charts.py` | Dependency-free server-side SVG line/ Bode chart builder |
| `static/app.js` | Progressive enhancement: show only the fields used by the selected analysis mode |
| `tests/test_spice_engine.py` | Netlist/parser/error-path tests that do not require ngspice |
| `AGENTS.md` | AI/engineering provenance rules for this repository |
| `README.md` (rewritten) | Clean setup/run/ngspice/validation instructions (resolves the stale merge conflict) |

## New interfaces

### `spice_engine.py`

- `validate_sim(raw: dict[str, str]) -> tuple[SimParams | None, dict[str, str]]`
- `build_netlist(params: SimParams) -> str`
- `run_simulation(params: SimParams, *, ngspice_bin=None, timeout=...) -> SimulationRun`
- `check_ngspice() -> dict` (available, path, version, model, message)
- `parse_op(path)`, `parse_ac(path)`, `parse_tran(path)` (public for tests)
- Exceptions: `SpiceUnavailable`, `SpiceError` (both carry `netlist` and `log`)

### `app.py`

- `POST /simulate` — validate, dispatch to `run_simulation`, render results/errors
- `GET /` — unchanged Lab 03 form, plus simulation defaults and engine status

## Expected outputs

| Analysis | ngspice command | Parsed data | UI |
|---|---|---|---|
| DC | `.op` | `VB, VE, VC, VCE, IC, IB, IE` | table + analytical comparison |
| AC | `.ac dec ...` | frequency, gain magnitude, phase | gain (dB) and phase charts, cutoff note |
| Transient | `.tran ...` | time, `v(source)`, `v(out)` | Vin/Vout waveform + peak-to-peak/gain |

All plots are built from the parsed `wrdata` files. No trace is hard-coded.

## Error paths

- ngspice executable missing → `SpiceUnavailable`; page shows an explicit error.
- Non-zero exit, timeout, missing/empty `wrdata` file, unparsable row →
  `SpiceError`; page shows the message, netlist and log.
- Invalid form values → per-field error, no netlist is run.
- **Never** render a stale plot or a “Success” badge when the solver did not
  actually produce fresh output.

## Verification

1. `pytest` — Lab 03 regression + new adapter/parser/error-path tests.
2. Real ngspice run on the reference circuit (DC/AC/Transient) — recorded in
   `docs/validation.md`.
3. Browser acceptance B1–B8 — recorded honestly as PASS/FAIL/NOT RUN.

## Environment note

This workstation currently has no `ngspice` executable. The adapter is
therefore built to fail loudly, and the validation record marks real SPICE
cases `NOT RUN` until ngspice is installed or `NGSPICE_BIN` is configured.
