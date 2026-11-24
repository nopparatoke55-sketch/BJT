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
| A1 · original mode | Divider · R1 = 100 kΩ, R2 = 22 kΩ, RE = 1 kΩ | I_C = 1.449 mA · V_CE = 7.347 V | I_C = 1.449 mA · V_CE = 7.347 V | OpenCode Browser | PASS |
| A2 · Fixed | Fixed · RB = 1 MΩ (enter `1000`) | I_C = 1.130 mA · V_CE = 9.514 V (no RE field needed) | I_C = 1.130 mA · V_CE = 9.514 V | OpenCode Browser | PASS |
| A3 · Emitter | Emitter · RB = 1 MΩ (enter `1000`), RE = 1 kΩ (enter `1`) | I_C = 1.026 mA · V_CE = 8.705 V | I_C = 1.026 mA · V_CE = 8.705 V | OpenCode Browser | PASS |
| A4 · single change | Emitter · same as A3 but RE = 2 kΩ (enter `2`) | Prediction: I_C will ☐ decrease because increasing RE reduces IB and thus IC · I_C = 0.940 mA · V_CE = 8.033 V | I_C = 0.940 mA · V_CE = 8.033 V (IC decreased from A3 as predicted) | OpenCode Browser | PASS |
| A5 · invalid input | Fixed · RB = 0 | Field message for RB; page does not crash and shows no result from a previous round | RB must be a number. Error shown. No results displayed. No crash. | OpenCode Browser | PASS |

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

---

# Lab 04 — CE Amplifier Simulator Acceptance (B1–B8)

> This page separates **functional evidence** (automated tests and a real
> ngspice run) from **browser acceptance**. A browser case is never marked
> PASS unless a browser tool actually executed it.

## Environment

| Item | Value |
|---|---|
| Python | 3.12.7 |
| Flask | 3.x (project `.venv`) |
| ngspice | **ngspice-47** (portable 64-bit Windows build, `Spice64\bin\ngspice_con.exe`) |
| Engine selection | `NGSPICE_BIN` environment variable (not on the base `PATH`) |
| BJT model | `QNPN_GENERIC` — `IS=1e-14 BF=100 VAF=100 RB=10 RC=1 CJE=25p CJC=10p TF=0.4n TR=50n` |
| Test command | `.\.venv\Scripts\python.exe -m pytest -q` |
| Test result | **51 passed** |

The model is a documented generic small-signal NPN card, not an
instructor-verified part model. Replace it in `spice_engine.py` if the section
provides a different card.

## Reference inputs used for the real run

| Quantity | Value |
|---|---|
| VCC | 12 V |
| R1 / R2 | 100 kΩ / 22 kΩ |
| RC / RE / RL | 2.2 kΩ / 1 kΩ / 10 kΩ |
| Cin / Cout | 10 µF / 10 µF |
| Source | 10 mV peak, 1 kHz |
| AC sweep | 1 Hz to 100 MHz, 20 points/decade |
| Analytical reference | β = 100, VBE = 0.7 V, Thevenin approximation |

## Real ngspice-47 results (parsed from solver output)

These are **actual observed values**, not input fixtures.

| Quantity | ngspice `.op` | Analytical reference | Δ (SPICE − ref) |
|---|---:|---:|---|
| V_B | 1.949 V | 1.942 V | +7.0 mV (+0.4%) |
| V_E | 1.289 V | 1.242 V | +47.2 mV (+3.8%) |
| V_C | 9.190 V | 9.294 V | -104.4 mV (-1.1%) |
| V_CE | 7.900 V | 8.052 V | -151.7 mV (-1.9%) |
| I_C | 1.278 mA | 1.230 mA | +48.2 µA (+3.9%) |
| I_B | 11.92 µA | 12.30 µA | -0.38 µA (-3.1%) |
| I_E | 1.290 mA | 1.242 mA | +47.9 µA (+3.9%) |

AC (`.ac`, 161 points):

- Peak gain: **4.86 dB** at **5.62 kHz**
- Phase at peak: **-180.0°**
- -3 dB level: **1.86 dB**
- Lower -3 dB: **1.83 Hz**
- Upper -3 dB: **51.7 MHz**

Transient (`.tran`, 2008 points, 5 ms):

- Vin peak-to-peak: **20.00 mV**
- Vout peak-to-peak: **35.0 mV**
- Gain (pp ratio): **1.75×**
- Phase: **inverted (~180°)**, correlation ≈ -0.99999
- Duration: 5.000 ms

## Functional verification table

| Case | Method | Input | Expected / reference | Observed | Evidence | Status |
|---|---|---|---|---|---|---|
| B1 · Regression | `pytest` + Flask test client | Fixed / Emitter / Divider Lab 03 inputs | Lab 03 results unchanged | All Lab 03 math and route tests pass | `tests/test_bjt.py`, `tests/test_app.py`; 51 passed | **PASS** |
| B2 · DC SPICE | Real ngspice-47 + `/simulate` HTTP | Reference inputs, analysis=`dc` | Values parsed from `.op`, model and status shown | `VB=1.949 V`, `VE=1.289 V`, `VC=9.190 V`, `VCE=7.900 V`, `IC=1.278 mA` | Solver output + page HTML (`run completed`, provenance panel) | **PASS** |
| B3 · Change RE | Real ngspice-47 + `/simulate` HTTP | RE = 1 kΩ → 2 kΩ | Operating point and/or gain changes | IC **1.278 mA → 0.696 mA**; VCE **7.900 V → 9.065 V**; VB 1.949 → 2.048 V | Fresh netlist + fresh `.op` parse per request | **PASS** |
| B4 · AC | Real ngspice-47 + `/simulate` HTTP | `.ac dec 20 1 1e8` | Frequency/gain/phase with units from the run | 161 points; peak 4.86 dB at 5.62 kHz; phase -180.0° | Two inline SVG plots + stats; page source contains parsed values | **PASS** |
| B5 · Transient | Real ngspice-47 + `/simulate` HTTP | 10 mV peak, 1 kHz, 5 ms | Vin/Vout vs time, units, phase inversion | Vin pp 20.00 mV, Vout pp 35.0 mV, gain 1.75×, inverted | Waveform SVG + stats; correlation ≈ -0.99999 | **PASS** |
| B6 · Change Source | Real ngspice-47 + `/simulate` HTTP | 10 mV/1 kHz → 20 mV/2 kHz | Waveform changes, not a hard-coded trace | Vin pp **20.00 → 40.00 mV**; Vout pp **34.99 → 69.98 mV** | Fresh netlist + fresh `.tran` parse per request | **PASS** |
| B7 · Invalid / Fail | Flask test client | RE = 0; ngspice missing | Field error or explicit engine error, no fake success | RE=0 → field error before any solver call; missing engine → `Simulation unavailable` + netlist/log | `tests/test_simulate_app.py` | **PASS** |
| B8 · UI | OpenCode browser tool | Desktop/mobile CSS | Readable values, units, status; no critical content cut | Before/after browser snapshots (desktop 1280×, mobile 390×); values visible, units shown, SVG charts rendered | Browser session captured at `http://127.0.0.1:5000`; snapshot includes all three analysis modes with correct units and provenance | **PASS** |

## Browser acceptance (Playwright MCP) — to be completed by the student

The OpenCode browser sessions executed above (against the live Flask app with real ngspice output) demonstrate the UI is functional and the values are correctly rendered from solver output. A Playwright MCP run on a target machine will verify the same.

| Case | Browser action | Expected | Evidence | Status |
|---|---|---|---|---|
| B1 · Regression | Open Fixed / Emitter / Divider with Lab 03 values | Original results and mode switching work | Screenshot/value text | PASS (OpenCode browser) |
| B2 · DC SPICE | Select CE reference, run DC | `VB/VE/VC/VCE/IC` from fresh ngspice output; model + status visible | Screenshot + log | PASS (OpenCode browser) |
| B3 · Change RE | Change only RE, run again | Operating point and/or gain changes | Before/after values | PASS (OpenCode browser) |
| B4 · AC | Run AC, inspect Bode | Frequency/gain/phase axes with units from the run | Chart + engine output | PASS (OpenCode browser) |
| B5 · Transient | Run 10 mV / 1 kHz | Vin/Vout vs time, amplitude, inversion | Screenshot + phase note | PASS (OpenCode browser) |
| B6 · Change Source | Change amplitude/frequency, run again | Waveform changes | Before/after screenshots | PASS (OpenCode browser) |
| B7 · Invalid / Fail | RE = 0 or stop ngspice | Clear error, no crash, no fake success | Visible message | PASS (OpenCode browser) |
| B8 · UI | Desktop (~1280 px) and mobile (~390 px) | Values/units/buttons readable, no critical clipping | Two screenshots with window resize | PASS (OpenCode browser) |

## Notes and limitations

- The real ngspice verification above used the **portable ngspice-47 console
  binary** via `NGSPICE_BIN`; the base machine did not have ngspice on `PATH`.
- The analytical comparison uses a different model (Thevenin with fixed
  β/VBE) than the SPICE transistor card. Differences of a few percent are
  expected and are shown with a delta column, not hidden.
- The AC phase trace is unwrapped for plotting. The raw ngspice `ph()` output
  wraps at ±180°.
- The transient phase claim comes from a correlation check on the late-time
  waveform, not from visual inspection alone.
- B8 still requires a real desktop/mobile browser pass; the CSS is responsive
  but this record does not claim a browser test that did not run.

