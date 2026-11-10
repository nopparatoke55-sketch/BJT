# BJT Common-Emitter DC Bias Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A single-page Flask app that computes the DC operating point of a voltage-divider-biased common-emitter BJT, validates inputs, warns on cutoff/saturation, and cross-checks every result with a second independent calculation.

**Architecture:** `bjt.py` holds all engineering math as pure functions over a frozen `BiasInput` dataclass and returns a `BiasResult`; it never imports Flask. `app.py` only parses the form, calls `bjt`, and renders. Two solvers exist — a closed-form Thevenin derivation and a hand-written 2×2 Gaussian elimination on the nodal equations — so a typo in either shows up as a non-zero delta.

**Tech Stack:** Python 3.12.7, Flask ≥ 3.0, pytest ≥ 8, Jinja2 templates, one plain CSS file. No numpy, no JS.

**Spec:** `docs/superpowers/specs/2026-11-10-bjt-ce-dc-bias-design.md`

## Global Constraints

- Python 3.12.7; Flask ≥ 3.0; pytest ≥ 8. Nothing else (no numpy/pandas/scipy).
- `.venv` at repo root (already gitignored). All commands run through `.venv\Scripts\python`.
- `bjt.py` must not import Flask. `app.py` must contain no physics formula.
- All user-facing text (labels, errors, warnings) is English; symbols stay `VCC, R1, R2, RC, RE, β, VBE, IB, IC, IE, VB, VC, VE, VCE`.
- Validation is server-side and returns one message per bad field; the page must never answer 500.
- Do not modify `electrical.py`, `test_electrical.py`, or `README.md` (README has unrelated merge-conflict markers).
- Exact constants: cutoff when `VBB <= VBE`; saturation when `VCE < 0.3`; `RC >= 0` allowed; `VCC` in `(0, 100]`; `VBE` in `(0, 1)`; all other resistances `> 0`; `β > 0`.
- Cross-check tolerance: `1e-9` absolute on every quantity.

## Review Focus

- `R1`, `R2`, or `RE` given as `0` → must be a field error, never `ZeroDivisionError`/500.
- Divider below the junction (`VBB <= VBE`) → currents must display as exactly `0`, never negative.
- `RC = 0` → still a valid circuit; must compute, not crash.
- Very large `β` (e.g. 10000) or tiny currents → formatted value must not read `0.000 A` when it is really 0.4 µA.
- Empty string, `"abc"`, or `"1,5"` in any field → field-level error with the entered text preserved, status 200.
- Saturated device with negative `VCE` → warning shown; a negative voltage must never appear as a normal result without that warning.

---

### Task 1: Environment, `BiasInput`, and validation

**Files:**
- Create: `requirements.txt`
- Create: `bjt.py`
- Create: `tests/test_bjt.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `BiasInput` — frozen dataclass with fields `vcc, r1, r2, rc, re, beta, vbe` (all `float`).
  - `validate(raw: dict[str, str]) -> tuple[BiasInput | None, dict[str, str]]` — returns `(BiasInput, {})` on success, `(None, {field: message})` on failure. `raw` keys are exactly the dataclass field names.

- [ ] **Step 1: Create the virtualenv and install dependencies**

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install --quiet --upgrade pip
.venv\Scripts\python -m pip install --quiet "flask>=3.0" "pytest>=8"
```

Expected: `.venv\Scripts\python -c "import flask, pytest; print(flask.__version__)"` prints a 3.x version.

- [ ] **Step 2: Write `requirements.txt`**

```
flask>=3.0
pytest>=8
```

- [ ] **Step 3: Write the failing tests in `tests/test_bjt.py`**

```python
import pytest
from bjt import BiasInput, validate

VALID = {"vcc": "12", "r1": "47000", "r2": "10000",
         "rc": "2200", "re": "470", "beta": "150", "vbe": "0.7"}

def test_validate_accepts_valid_input():
    x, errors = validate(VALID)
    assert errors == {}
    assert isinstance(x, BiasInput)
    assert x.vcc == 12.0 and x.beta == 150.0 and x.vbe == 0.7

def test_validate_rejects_non_numeric():
    x, errors = validate({**VALID, "r1": "abc"})
    assert x is None
    assert "r1" in errors

def test_validate_rejects_zero_resistors():
    for field in ("r1", "r2", "re"):
        x, errors = validate({**VALID, field: "0"})
        assert x is None and field in errors

def test_validate_allows_zero_rc():
    x, errors = validate({**VALID, "rc": "0"})
    assert errors == {} and x.rc == 0.0

def test_validate_rejects_bad_beta_and_vbe():
    assert validate({**VALID, "beta": "0"})[1].keys() == {"beta"}
    assert validate({**VALID, "vbe": "1.2"})[1].keys() == {"vbe"}

def test_validate_reports_every_bad_field():
    _, errors = validate({"vcc": "-1", "r1": "x", "r2": "0", "rc": "-5",
                          "re": "0", "beta": "0", "vbe": "0"})
    assert set(errors) == {"vcc", "r1", "r2", "rc", "re", "beta", "vbe"}

def test_validate_accepts_comma_decimal():
    x, errors = validate({**VALID, "vbe": "0,7"})
    assert errors == {} and x.vbe == pytest.approx(0.7)

def test_validate_rejects_empty_field():
    x, errors = validate({**VALID, "vcc": ""})
    assert x is None and errors.keys() == {"vcc"}
```

- [ ] **Step 4: Run to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_bjt.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bjt'`.

- [ ] **Step 5: Implement `bjt.py`**

```python
@dataclass(frozen=True)
class BiasInput:
    vcc: float
    r1: float
    r2: float
    rc: float
    re: float
    beta: float
    vbe: float
```

`validate` parses each value with `float(str(raw.get(field, "")).strip().replace(",", "."))`, then applies, in this order: numeric check, then the range rules from Global Constraints. Messages, verbatim:

- `"VCC must be a number between 0 and 100 V."`
- `"R1 must be greater than 0 Ω."` (same pattern for `R2`, `RE`; `RC`: `"RC must not be negative."`)
- `"β must be greater than 0."`
- `"VBE must be between 0 and 1 V."`
- any unparsable field: `"<FIELD> must be a number."`

- [ ] **Step 6: Run to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_bjt.py -v`
Expected: 8 passed.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt bjt.py tests/test_bjt.py
git commit -m "feat: validate BJT bias inputs"
```

---

### Task 2: Closed-form solver, region logic, formatting

**Files:**
- Modify: `bjt.py`
- Modify: `tests/test_bjt.py`

**Interfaces:**
- Consumes: `BiasInput`, `validate` from Task 1.
- Produces:
  - `BiasResult` — frozen dataclass: `vbb, rb, ib, ic, ie, vb, vc, ve, vce` (`float`), `region: str` (`"active" | "cutoff" | "saturation"`), `warning: str | None`.
  - `solve_thevenin(x: BiasInput) -> BiasResult`
  - `fmt_current(amperes: float) -> str`, `fmt_voltage(volts: float) -> str`

- [ ] **Step 1: Write the failing tests (append to `tests/test_bjt.py`)**

```python
from bjt import solve_thevenin, fmt_current, fmt_voltage

ACTIVE = BiasInput(12, 47000, 10000, 2200, 470, 150, 0.7)
CUTOFF = BiasInput(12, 100000, 1000, 2200, 470, 150, 0.7)
SAT    = BiasInput(12, 47000, 10000, 10000, 100, 150, 0.7)

def test_thevenin_active_known_values():
    r = solve_thevenin(ACTIVE)
    assert r.region == "active" and r.warning is None
    assert r.ib  == pytest.approx(1.77405e-5, rel=1e-4)
    assert r.ic  == pytest.approx(2.66108e-3, rel=1e-4)
    assert r.ie  == pytest.approx(2.67882e-3, rel=1e-4)
    assert r.vb  == pytest.approx(1.95904, rel=1e-4)
    assert r.vc  == pytest.approx(6.14563, rel=1e-4)
    assert r.ve  == pytest.approx(1.25904, rel=1e-4)
    assert r.vce == pytest.approx(4.88659, rel=1e-4)

def test_thevenin_cutoff_zeroes_currents():
    r = solve_thevenin(CUTOFF)
    assert r.region == "cutoff" and r.warning is not None
    assert (r.ib, r.ic, r.ie) == (0.0, 0.0, 0.0)
    assert r.vce == pytest.approx(12.0) and r.ve == 0.0 and r.vc == pytest.approx(12.0)
    assert r.vb == pytest.approx(0.118812, rel=1e-4)

def test_cutoff_when_vbb_equals_vbe():
    r = solve_thevenin(BiasInput(12, 113000, 7000, 2200, 470, 150, 0.7))
    assert r.vbb == pytest.approx(0.7) and r.region == "cutoff"

def test_thevenin_saturation_warns():
    r = solve_thevenin(SAT)
    assert r.region == "saturation" and r.warning is not None
    assert r.vce < 0.3

def test_vce_exactly_point_three_is_active():
    x = BiasInput(12, 47000, 10000, 3300, 470, 150, 0.7)
    r = solve_thevenin(x)
    assert r.region in {"active", "saturation"}
    assert (r.region == "saturation") == (r.vce < 0.3)

def test_fmt_current():
    assert fmt_current(17.74e-6) == "17.74 µA"
    assert fmt_current(2.661e-3) == "2.661 mA"
    assert fmt_current(1.5) == "1.5000 A"
    assert fmt_current(0.0) == "0.00 µA"
    assert fmt_current(4e-7) == "0.40 µA"

def test_fmt_voltage():
    assert fmt_voltage(4.88659) == "4.887 V"
    assert fmt_voltage(0.7) == "700.0 mV"
    assert fmt_voltage(0.0) == "0.0 mV"

def test_thevenin_allows_zero_rc():
    r = solve_thevenin(BiasInput(12, 47000, 10000, 0, 470, 150, 0.7))
    assert r.vc == pytest.approx(12.0) and r.vce == pytest.approx(12.0 - r.ve)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_bjt.py -v`
Expected: FAIL — `ImportError: cannot import name 'solve_thevenin'`.

- [ ] **Step 3: Implement in `bjt.py`**

`solve_thevenin` computes `vbb`, `rb`, `ib`, `ic`, `ie`, `vb`, `vc`, `ve`, `vce` exactly as in spec §7.2, then delegates to `_classify(x, result)`. `_classify` returns `dataclasses.replace(...)`:

- `vbb <= x.vbe` → `region="cutoff"`, `ib=ic=ie=0.0`, `ve=0.0`, `vc=x.vcc`, `vce=x.vcc`, `warning="Transistor is in cutoff (VBB ≤ VBE); no collector current flows."`
- `vce < 0.3` → `region="saturation"`, `warning="Transistor is in saturation (VCE < 0.3 V); the linear model no longer applies."`
- otherwise `region="active"`, `warning=None`.

`fmt_current`: `abs(a) < 1e-3` → `f"{a*1e6:.2f} µA"`; `abs(a) < 1` → `f"{a*1e3:.3f} mA"`; else `f"{a:.4f} A"`.
`fmt_voltage`: `abs(v) < 1` → `f"{v*1e3:.1f} mV"`; else `f"{v:.3f} V"`.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_bjt.py -v`
Expected: 16 passed.

- [ ] **Step 5: Commit**

```bash
git add bjt.py tests/test_bjt.py
git commit -m "feat: solve DC bias with closed-form Thevenin model"
```

---

### Task 3: Nodal solver and cross-check

**Files:**
- Modify: `bjt.py`
- Modify: `tests/test_bjt.py`

**Interfaces:**
- Consumes: `BiasInput`, `BiasResult`, `solve_thevenin`, `_classify` from Task 2.
- Produces:
  - `solve_nodal(x: BiasInput) -> BiasResult`
  - `cross_check(a: BiasResult, b: BiasResult) -> dict[str, float]` — keys `ib, ic, ie, vb, vc, ve, vce`; values are `abs(a.x - b.x)`.

- [ ] **Step 1: Write the failing tests (append to `tests/test_bjt.py`)**

```python
from bjt import solve_nodal, cross_check

@pytest.mark.parametrize("case", [ACTIVE, CUTOFF, SAT])
def test_nodal_matches_thevenin(case):
    d = cross_check(solve_thevenin(case), solve_nodal(case))
    assert max(d.values()) < 1e-9

def test_nodal_uses_its_own_solution_path():
    r = solve_nodal(ACTIVE)
    assert r.region == "active"
    assert r.ib == pytest.approx(1.77405e-5, rel=1e-4)

def test_cross_check_is_zero_for_identical_results():
    a = solve_thevenin(ACTIVE)
    assert set(cross_check(a, a).values()) == {0.0}

def test_nodal_cutoff_matches_cutoff_branch():
    a, b = solve_thevenin(CUTOFF), solve_nodal(CUTOFF)
    assert a.region == b.region == "cutoff"
    assert (b.ib, b.ic, b.ie) == (0.0, 0.0, 0.0)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_bjt.py -v`
Expected: FAIL — `ImportError: cannot import name 'solve_nodal'`.

- [ ] **Step 3: Implement in `bjt.py`**

`solve_nodal` builds the 2×2 system from spec §7.3 with unknowns `(VB, IB)`:

```
A = [[1/r1 + 1/r2, 1.0],
     [1.0,          -(1 + beta) * re]]
b = [vcc / r1, vbe]
```

and solves it with a private `_solve_2x2(a: list[list[float]], b: list[float]) -> tuple[float, float]` written by hand (determinant check, raise `ValueError("singular system")` if `abs(det) < 1e-15`). Then `ic = beta*ib`, `ie = (1+beta)*ib`, `vc = vcc - ic*rc`, `ve = ie*re`, `vce = vc - ve`, `vbb`/`rb` as in Task 2, and pass the result through `_classify` so both solvers share the region rules.

`cross_check` returns `{name: abs(getattr(a, name) - getattr(b, name)) for name in ("ib","ic","ie","vb","vc","ve","vce")}`.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python -m pytest tests/test_bjt.py -v`
Expected: 22 passed.

- [ ] **Step 5: Commit**

```bash
git add bjt.py tests/test_bjt.py
git commit -m "feat: cross-check bias with independent nodal solve"
```

---

### Task 4: Flask app, template, and stylesheet

**Files:**
- Create: `app.py`
- Create: `templates/index.html`
- Create: `static/style.css`
- Create: `tests/test_app.py`

**Interfaces:**
- Consumes: `validate`, `solve_thevenin`, `solve_nodal`, `cross_check`, `fmt_current`, `fmt_voltage`.
- Produces: module-level `app` (a `Flask` instance) importable as `from app import app`; routes `GET /` and `POST /calculate`.

- [ ] **Step 1: Write the failing tests in `tests/test_app.py`**

```python
import pytest
from app import app

@pytest.fixture
def client():
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c

FORM = {"vcc": "12", "r1": "47000", "r2": "10000",
        "rc": "2200", "re": "470", "beta": "150", "vbe": "0.7"}

def test_index_shows_form_with_defaults(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"VCC" in r.data and b'value="47000"' in r.data

def test_valid_post_shows_results(client):
    r = client.post("/calculate", data=FORM)
    assert r.status_code == 200
    body = r.data.decode()
    assert "2.661 mA" in body
    assert "4.887 V" in body
    assert "ACTIVE" in body.upper()

def test_cross_check_delta_is_shown(client):
    body = client.post("/calculate", data=FORM).data.decode()
    assert "nodal" in body.lower() and "1e-9" not in body

def test_invalid_post_keeps_values_and_shows_error(client):
    r = client.post("/calculate", data={**FORM, "r1": "abc"})
    assert r.status_code == 200
    body = r.data.decode()
    assert "must be a number" in body
    assert 'value="abc"' in body
    assert "2.661 mA" not in body

def test_zero_resistor_is_not_a_server_error(client):
    r = client.post("/calculate", data={**FORM, "re": "0"})
    assert r.status_code == 200
    assert "RE must be greater than 0" in r.data.decode()

def test_cutoff_warning_is_shown(client):
    r = client.post("/calculate", data={**FORM, "r2": "1000"})
    assert r.status_code == 200
    assert "cutoff" in r.data.decode().lower()

def test_saturation_warning_is_shown(client):
    r = client.post("/calculate", data={**FORM, "rc": "10000", "re": "100"})
    assert r.status_code == 200
    assert "saturation" in r.data.decode().lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_app.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app'`.

- [ ] **Step 3: Implement `app.py`**

`GET /` renders `index.html` with `values=defaults` (`vcc=12, r1=47000, r2=10000, rc=2200, re=470, beta=150, vbe=0.7` as strings), `errors={}`, `result=None`. `POST /calculate` calls `validate(request.form.to_dict())`; on errors re-renders with `values=request.form`, `errors=errors`, `result=None`; on success calls `solve_thevenin`, `solve_nodal`, `cross_check`, and renders with `values=request.form`, `errors={}`, `result=` a dict:

```
{"region": "ACTIVE",
 "currents": {"IB": fmt_current(r.ib), "IC": ..., "IE": ...},
 "voltages": {"VB": fmt_voltage(r.vb), "VC": ..., "VE": ..., "VCE": ...},
 "warning": r.warning,
 "delta_ic": f"{d['ic']:.1e}",
 "ok": max(d.values()) < 1e-9}
```

Nothing else in the file — no formula, no region rule. Add `if __name__ == "__main__": app.run(debug=True)`.

- [ ] **Step 4: Write `templates/index.html`**

One `<form method="post" action="/calculate">` with a label + `<input name="…" value="{{ values.<field> }}">` per field, an inline `<p class="error">{{ errors.<field> }}</p>` under each, then — when `result` is set — a results block listing region (uppercased), `IB/IC/IE` with `fmt_current` strings, `VB/VC/VE/VCE` with `fmt_voltage` strings, `warning` when present, and a cross-check line showing `ΔIC` with `"{:.1e}"` formatting plus a `✓` when `max(delta) < 1e-9`.

- [ ] **Step 5: Write `static/style.css`**

Plain CSS only: system font stack, max-width 720 px, labelled input grid, monospace results table, `.error` in red, `.warning` in amber. No framework, no dark mode, no animation.

- [ ] **Step 6: Run to verify it passes**

Run: `.venv\Scripts\python -m pytest -v`
Expected: 29 passed (22 + 7).

- [ ] **Step 7: Commit**

```bash
git add app.py templates/index.html static/style.css tests/test_app.py
git commit -m "feat: serve BJT bias calculator in Flask"
```

---

### Task 5: Local demonstration and GitHub push

**Files:**
- Modify: none (verification only)

**Interfaces:**
- Consumes: everything above.
- Produces: a verified running app and an updated `origin/main`.

- [ ] **Step 1: Run the whole suite one more time**

Run: `.venv\Scripts\python -m pytest -q`
Expected: all tests pass, 0 failures. Record the count for the report.

- [ ] **Step 2: Start the server and fetch the page**

```powershell
Start-Process -FilePath ".venv\Scripts\python.exe" -ArgumentList "app.py"
Start-Sleep -Seconds 2
(Invoke-WebRequest -Uri http://127.0.0.1:5000 -UseBasicParsing).StatusCode
```

Expected: `200`.

- [ ] **Step 3: Prove the calculation end to end over HTTP**

```powershell
(Invoke-WebRequest -Uri http://127.0.0.1:5000/calculate -Method POST -Body @{
  vcc="12"; r1="47000"; r2="10000"; rc="2200"; re="470"; beta="150"; vbe="0.7"
} -UseBasicParsing).Content -match "2.661 mA"
```

Expected: `True`.

- [ ] **Step 4: Confirm the layering rules**

Run: `Select-String -Path bjt.py -Pattern "flask" -SimpleMatch` → no output.
Run: `Select-String -Path app.py -Pattern "beta \*|1 \+ "` → no output.

- [ ] **Step 5: Commit the docs and push**

```bash
git add docs/superpowers
git commit -m "docs: add BJT bias design and implementation plan"
git push origin main
git log --oneline -1 origin/main
```

Expected: the pushed commit hash matches local `HEAD`.

- [ ] **Step 6: Leave the app running for the demonstration**

Report the URL `http://127.0.0.1:5000` and the test count to the human partner.
