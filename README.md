# ENG29 2121 — BJT Common-Emitter Labs (Lab 03 + Lab 04)

A single-page Flask application for the Common-Emitter BJT laboratory.

- **Lab 03 (preserved):** analytical DC-bias calculator for Voltage Divider,
  Fixed and single-supply Emitter bias.
- **Lab 04 (added):** real `ngspice` simulation of one reference
  **CE voltage-divider amplifier** — DC operating point (`.op`), AC frequency
  response (`.ac`) and transient response (`.tran`) — with plots built from the
  solver output and explicit provenance.

The app never fabricates a SPICE result. If ngspice is missing or a run fails,
the page shows an error, the generated netlist and the solver log instead of a
stale graph or a fake “Success” badge.

---

## 1. Features

### Lab 03 — analytical DC bias

- Three bias modes: **Voltage Divider**, **Fixed**, **Emitter (single supply)**.
- Server-side validation with one message per field.
- Active / cutoff / saturation classification and warnings.
- Voltage-divider result cross-checked by an independent nodal 2×2 solve.
- All Lab 03 tests still run.

### Lab 04 — real ngspice simulation

| Analysis | ngspice command | Displayed data |
|---|---|---|
| DC | `.op` | `VB, VE, VC, VCE, IC, IB, IE` + analytical comparison |
| AC | `.ac dec …` | Bode gain (dB) and phase, peak gain, −3 dB crossings |
| Transient | `.tran …` | `Vin`/`Vout` waveform, peak-to-peak values, gain, phase inversion |

Additional engineering safeguards:

- Netlist generated from the validated, unit-converted form values.
- `subprocess.run([...])` with a list argument, a timeout and a fresh temporary
  working directory per run — no `shell=True`.
- ASCII `wrdata` output parsed by a tolerant, tested parser.
- SPICE values and analytical reference values are shown in separate columns
  with a delta and a note explaining the different models.
- Cutoff frequencies are reported only when a −3 dB crossing exists inside the
  swept range; otherwise the UI says “not determined in sweep range”.

---

## 2. Repository layout

```text
app.py                     Flask routes + form handling + display formatting
bjt.py                     Lab 03 analytical BJT math (unchanged)
spice_engine.py            Lab 04 ngspice adapter: validate → netlist → run → parse
charts.py                  Dependency-free inline-SVG chart builder
templates/index.html       Lab 03 form/results + Lab 04 simulation section
static/style.css           Responsive UI styling
static/app.js              Progressive enhancement for analysis-specific fields
tests/test_bjt.py          Lab 03 engineering math tests
tests/test_app.py          Lab 03 Flask route tests
tests/test_spice_engine.py Lab 04 netlist/parser/error-path tests
tests/test_simulate_app.py Lab 04 /simulate rendering and failure-path tests
docs/validation.md         Browser/regression acceptance record
docs/superpowers/          Lab 03 design plan + Lab 04 integration plan
requirements.txt           Flask + pytest
AGENTS.md                  Engineering/AI provenance rules
```

---

## 3. Requirements

- Python 3.12 (tested with 3.12.7)
- Flask ≥ 3.0
- pytest ≥ 8
- **ngspice** for the Lab 04 simulation section

No chart library and no numpy/pandas are required; plots are generated as
inline SVG on the server.

---

## 4. Setup

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

On macOS/Linux use `.venv/bin/python` instead of `.venv\Scripts\python.exe`.

### Install ngspice

The simulation section needs a working `ngspice` executable.

**Windows (portable, recommended for the lab):**

1. Download the 64-bit 7z package from
   <https://ngspice.sourceforge.io/download.html>.
2. Extract it, for example to `C:\tools\ngspice-47`.
3. Use the console executable:
   `C:\tools\ngspice-47\Spice64\bin\ngspice_con.exe`.

**macOS:** `brew install ngspice`

**Linux:** install `ngspice` with your distribution package manager.

### Point the app at ngspice

If `ngspice` / `ngspice_con` is on `PATH`, no configuration is needed.
Otherwise set `NGSPICE_BIN` before starting Flask:

```powershell
# PowerShell — current session only
$env:NGSPICE_BIN = "C:\tools\ngspice-47\Spice64\bin\ngspice_con.exe"
```

```bash
# macOS / Linux
export NGSPICE_BIN=/usr/local/bin/ngspice
```

Verify:

```powershell
ngspice -v
# or
& $env:NGSPICE_BIN -v
```

The page header also shows the detected engine version, path and model name.

---

## 5. Run

```powershell
.\.venv\Scripts\python.exe app.py
```

Open <http://127.0.0.1:5000>.

1. Use the **Lab 03** form to reproduce the analytical DC-bias modes.
2. Scroll to **Lab 04 · SPICE Simulation — CE Voltage Divider**.
3. Choose `DC`, `AC` or `Transient`, adjust the reference values and press
   **Run**.
4. Read the engine status, values, units, plots and the expandable
   **Provenance** panel (netlist + ngspice log).

---

## 6. Reference circuit and model

The netlist implements the handout's reference CE voltage-divider stage:

- `VCC` → `R1`/`R2` base divider
- `RC` collector load, unbypassed `RE`
- NPN `Q1`
- `Cin` input coupling, `Cout` output coupling, `RL` load
- `VIN` ideal source with `DC 0`, `AC 1` and `SIN(0 amplitude frequency)`

Default form values (input fixture, not a result):

| Quantity | Default |
|---|---|
| VCC | 12 V |
| R1 / R2 | 100 kΩ / 22 kΩ |
| RC / RE / RL | 2.2 kΩ / 1 kΩ / 10 kΩ |
| Cin / Cout | 10 µF / 10 µF |
| Source | 10 mV peak, 1 kHz |
| AC sweep | 1 Hz → 100 MHz, 20 points/decade |

**Model:** `QNPN_GENERIC`

```spice
.model QNPN_GENERIC NPN(IS=1e-14 BF=100 VAF=100 RB=10 RC=1
+ CJE=25p CJC=10p TF=0.4n TR=50n)
```

This is a documented generic small-signal NPN card, not a claim about a
specific part. Replace `MODEL_CARD` / `MODEL_NAME` in `spice_engine.py` with the
instructor-verified model if your section provides one.

---

## 7. Provenance and limitations

- **SPICE results** come from parsing the files written by ngspice during that
  request (`op_data.txt`, `ac_data.txt`, `tran_data.txt`).
- **Analytical results** come from `bjt.py` using the Thevenin approximation
  with the β/VBE values shown on the page.
- The two are **different models**; they are not expected to match every digit.
- ngspice failure, timeout, missing output or invalid data is surfaced as an
  error with the log and netlist. No plot is rendered from stale data.
- The app is a local teaching tool; it is not hardened for public deployment.
- The baseline has no emitter bypass capacitor. Adding `CE` is optional future
  work and changes the AC model.

---

## 8. Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The suite covers:

- Lab 03 validation, solvers, region logic and formatters.
- Lab 03 Flask routes and error states.
- Lab 04 input validation, netlist generation and ASCII parsers.
- Lab 04 `/simulate` success, invalid-input, missing-engine and chart rendering
  paths.
- A stubbed subprocess flow proving the adapter parses fresh solver output
  rather than constants.

Real ngspice verification is recorded in [`docs/validation.md`](docs/validation.md).
It includes the engine version, model, exact inputs and observed values.

---

## 9. Troubleshooting

| Symptom | Check |
|---|---|
| “ngspice executable not found” | `ngspice -v` works? Set `NGSPICE_BIN` to the full executable path and restart Flask. |
| Run fails immediately | Open the **Provenance** panel; the ngspice log and netlist are shown. |
| No plots after AC/Transient | The run must succeed first; a failed run deliberately shows no graph. |
| `pytest` cannot import `app` | Run pytest from the repository root with the project virtual environment. |
| Port 5000 already in use | Stop the other Flask process or set a different port in `app.py`. |

---

## 10. Submission evidence

The Lab 04 handout expects:

- this repository URL and commit SHA,
- a working Flask app with the three Lab 03 modes plus real CE SPICE
  DC/AC/Transient,
- this README and `docs/validation.md`,
- before/after UI notes and real browser screenshots,
- a short note on what the AI changed and what the student verified.

`docs/validation.md` is the single place where acceptance cases are recorded.
Never mark a case `PASS` unless the browser or tool actually executed it.

---

## 11. Repository history

This README replaces a stale unresolved merge-conflict block that was present
in the repository before the Lab 04 work. The Lab 03 application files and
tests were preserved; the Lab 04 additions are described above.
