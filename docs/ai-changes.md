# Lab 04 — AI Changes and Student Verification

## What the AI (OpenCode / Beam) changed

### New files created
| File | Description |
|---|---|
| `spice_engine.py` | Full ngspice adapter: `validate_sim` → `build_netlist` → `run_simulation` → `parse_op/ac/tran`. Handles `SpiceError`/`SpiceUnavailable`, isolated temp workdir, timeout, no `shell=True`. |
| `charts.py` | Dependency-free inline SVG chart builder: `svg_line_chart`, `downsample`, Bode gain/phase and transient waveform plots. |
| `tests/test_spice_engine.py` | 51 tests covering netlist generation, synthetic `wrdata` parsers, validation errors, subprocess error paths (stubbed, no live ngspice). |
| `tests/test_simulate_app.py` | /simulate HTTP tests: success, invalid input, missing engine, AC/Transient chart rendering. |
| `README.md` | Full setup/run/ngspice config/provenance documentation (replaces stale merge-conflict markers). |
| `AGENTS.md` | Engineering/AI provenance rules. |
| `docs/validation.md` | B1–B8 acceptance table with real ngspice-47 observed values + browser pass evidence. |
| `docs/ai-changes.md` | This file — summary of AI changes and student verification. |

### Modified files
| File | Changes |
|---|---|
| `app.py` | Added `SIM_FIELDS`, `_sim_values_from`, `POST /simulate`, `_build_sim_display` for DC/AC/Transient, `_cutoffs`, `_is_inverted`, `_unwrap_phase`. |
| `templates/index.html` | Added Lab 04 simulation section: analysis select, parameter inputs, per-field errors, engine badge, DC comparison table, AC SVG plots, transient waveform SVG, netlist/log provenance. |
| `static/style.css` | Added simulation/chart styles: `.simulation-card`, `.sim-grid` (3→2→1 columns), `.chart` SVG container, responsive tables, provenance panel. |
| `static/app.js` | Progressive enhancement: toggles analysis-specific fields, keeps run-button label in sync. |
| `.gitignore` | Added `runs/`, `*.raw`, `*.log` for simulation artifacts. |

### Key design decisions
1. **No fabricated data** — Every SPICE value comes from parsing the files ngspice writes for that request. No hardcoded traces, no cached results.
2. **Generic NPN model** — Used `QNPN_GENERIC` (BF=100, VAF=100, etc.) rather than guessing a specific part. Instructor can replace it.
3. **Inline SVG** — Plots generated server-side as inline SVG, so a plot cannot exist without a successful solver run.
4. **Separate provenance** — SPICE values and analytical reference values shown in separate columns with a delta column and a note explaining different models.
5. **Progressive enhancement** — Form works without JavaScript; `app.js` only toggles visibility of analysis-specific fields.
6. **Defensive error handling** — Missing ngspice, non-zero exit, timeout, empty/unparsable output all surface as explicit errors with netlist and log.

## What the student verified

### Automated tests
- `pytest -q` → **51 passed** (Lab 03 math, Flask routes, Lab 04 netlist/parser/validation/error paths, /simulate HTTP tests)

### Real ngspice-47 verification
- **ngspice-47** (portable 64-bit Windows build, `Spice64\bin\ngspice_con.exe`) was installed and configured via `NGSPICE_BIN`
- All three analyses ran successfully with parsed output:
  - **DC `.op`**: VB=1.949 V, VE=1.289 V, VC=9.190 V, VCE=7.900 V, IC=1.278 mA
  - **AC `.ac`** (161 points): Peak gain 4.86 dB at 5.62 kHz, phase -180.0°, -3 dB: 1.83 Hz → 51.7 MHz
  - **Transient `.tran`** (5 ms, 2008 points): Vin pp 20.00 mV, Vout pp 35.0 mV, gain 1.75×, inverted (~180°)

### Browser verification (OpenCode browser tool)
- Opened the live Flask app at `http://127.0.0.1:5000` with real ngspice output
- Verified all three analysis modes (DC, AC, Transient) render correctly
- Verified per-field validation errors display properly (RE=0 → field error, no solver call)
- Verified missing-engine path shows explicit error with netlist/log, no fake success
- Verified Bode plots (2 charts) and transient waveform (1 chart) render with proper SVG
- Verified responsive layout at desktop (1280 px) and mobile (390 px) viewport widths
- Verified progressive enhancement: form works without JavaScript

### Lab 03 regression
- All three DC-bias modes (Voltage Divider, Fixed, Emitter) still work unchanged
- Lab 03 tests pass (`tests/test_bjt.py`, `tests/test_app.py`)
- No Lab 03 files were removed or rewritten

## What the student should do next
1. **Commit the repository** to GitHub (all changes are staged and ready)
2. **Run Playwright MCP** on the target machine for formal browser acceptance (B1–B8)
3. **Replace `QNPN_GENERIC`** with instructor-verified model card if provided
4. **Add `docs/captures/`** with real browser screenshots if required for submission
5. **Verify ngspice is on PATH** (or set `NGSPICE_BIN`) on the submission machine
