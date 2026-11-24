# Lab 04 — CE Amplifier Simulator
## B1–B9 Acceptance Table (Real ngspice + Browser)

| Case | Method | Input | Expected / Reference | Observed | Evidence | Status |
|------|--------|-------|----------------------|----------|----------|--------|
| **B1 · Regression** | `pytest` + Flask test client | Fixed / Emitter / Divider Lab 03 inputs | Lab 03 results unchanged | All Lab 03 math and route tests pass | `tests/test_bjt.py`, `tests/test_app.py`; 51 passed | **PASS** |
| **B2 · DC SPICE** | Real ngspice-47 + `/simulate` HTTP | Reference inputs, analysis=`dc` | Values parsed from `.op`, model and status shown | `VB=1.949 V`, `VE=1.289 V`, `VC=9.190 V`, `VCE=7.900 V`, `IC=1.278 mA` | Solver output + page HTML (`run completed`, provenance panel) | **PASS** |
| **B3 · Change RE** | Real ngspice-47 + `/simulate` HTTP | RE = 1 kΩ → 2 kΩ | Operating point and/or gain changes | IC **1.278 mA → 0.696 mA**; VCE **7.900 V → 9.065 V**; VB 1.949 → 2.048 V | Fresh netlist + fresh `.op` parse per request | **PASS** |
| **B4 · AC** | Real ngspice-47 + `/simulate` HTTP | `.ac dec 20 1 1e8` | Frequency/gain/phase/units from the run | 161 points; peak 4.86 dB at 5.62 kHz; phase -180.0° | Two inline SVG plots + stats; page source contains parsed values | **PASS** |
| **B5 · Transient** | Real ngspice-47 + `/simulate` HTTP | 10 mV peak, 1 kHz, 5 ms | Vin/Vout vs time, units, phase inversion | Vin pp 20.00 mV, Vout pp 35.0 mV, gain 1.75×, inverted (~180°) | Waveform SVG + stats; correlation ≈ -0.99999 | **PASS** |
| **B6 · Change Source** | Real ngspice-47 + `/simulate` HTTP | 10 mV/1 kHz → 20 mV/2 kHz | Waveform changes, not a hard-coded trace | Vin pp **20.00 → 40.00 mV**; Vout pp **34.99 → 69.98 mV** | Fresh netlist + fresh `.tran` parse per request | **PASS** |
| **B7 · Invalid / Fail** | Flask test client | RE = 0; ngspice missing | Field error or explicit engine error, no fake success | RE=0 → field error before any solver call; missing engine → `Simulation unavailable` + netlist/log | `tests/test_simulate_app.py` | **PASS** |
| **B8 · UI** | OpenCode browser tool | Desktop/mobile CSS | Readable values, units, status; no critical content cut | Before/after browser snapshots (desktop 1280×, mobile 390×); values visible, units shown, SVG charts rendered | Browser session captured at `http://127.0.0.1:5000`; snapshot includes all three analysis modes with correct units and provenance | **PASS** |
| **B9 · Screen target** | OpenCode browser tool + Flask test client | Handout wireframe | Circuit & Parameters left, Simulation & Plots centre, Engineering Results right; no fake traces; units render as kΩ / µF / µs | Workbench grid measured as 343 px / 441 px / 294 px at desktop width; empty-state says plots appear only after a real run; AC run produced 2 parsed SVG plots; R2 upper and lower leads connected; browser DOM shows `100 / 22 kΩ`, `10 / 10 µF`, `Units: kΩ · µF · mV peak · Hz.` with no `?` placeholders | `test_index_has_three_column_workbench_and_no_placeholder_plots`; `test_simulation_units_are_not_replaced_by_question_marks`; browser DOM inspection and screenshots | **PASS** |

---

### Quick reference: Unit rendering

| Field | Correct symbol | Location |
|-------|----------------|----------|
| Resistors | `kΩ` | `templates/index.html` `.sim-ref-list dd`, `.sim-field .unit` |
| Capacitors | `µF` | `templates/index.html` `.sim-ref-list dd`, `.sim-field .unit` |
| Time step | `µs` | `templates/index.html` `.sim-field[data-analysis="tran"] #sim_tstep .unit` |
| Reference β | `β` (Greek beta) | `templates/index.html` `.sim-field label[for="sim_beta_ref"]` |
| AC sweep | `→` (arrow) | `templates/index.html` AC start/stop labels |
| Gain/Phase labels | `°`, `·`, `−3 dB` | `templates/index.html` `.sim-stats`, `.sim-ref-list` |
| Source amplitude | `mV · Hz` | `templates/index.html` source line |
| Form note | `kΩ · µF · mV peak · Hz.` | `templates/index.html` `.form-note` |

---

### Evidence files (screenshots)

| File | Description |
|------|-------------|
| `docs/captures/lab04-workbench-layout.jpeg` | Initial three-column workbench (desktop 1280 px) |
| `docs/captures/lab04-ac-real-run.jpeg` | AC run with parsed Bode & waveform SVG plots |
| `docs/captures/` folder | Holds all browser‑captured PNGs for B8 / B9 |

---

### Test suite summary

```text
pytest -q → 53 passed
  • 51 tests cover Lab 03 math, Flask routes, spice_engine netlist/parser/validation/error paths
  • 2 new tests added in this run:
    - test_index_has_three_column_workbench_and_no_placeholder_plots
    - test_simulation_units_are_not_replaced_by_question_marks
```