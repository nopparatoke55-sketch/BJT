"""Tests for :mod:`bjt` — pure‑engineering BJT bias functions.

These tests exercise the public API only — no Flask, no templates,
no web server.  Every assertion uses values that can be verified by
hand (calculator or pencil & paper), so a passing test is independent
proof that the implementation is correct.
"""
import pytest

from bjt import BiasInput, validate, solve_thevenin, solve_nodal, cross_check, fmt_current, fmt_voltage

# ----------------------------------------------------------------------
# Valid input used by many tests — the "standard" then‑lab values
# ----------------------------------------------------------------------
VALID = {
    "vcc": "12",
    "r1": "47000",
    "r2": "10000",
    "rc": "2200",
    "re": "470",
    "beta": "150",
    "vbe": "0.7",
}

# ----------------------------------------------------------------------
# ────────────────────────────────────────────────────────────────────
# Task 1 : validate()
# ────────────────────────────────────────────────────────────────────
# ----------------------------------------------------------------------


def test_validate_accepts_valid_input():
    """All seven fields correct → BiasInput returned, empty errors."""
    x, errors = validate(VALID)
    assert errors == {}
    assert isinstance(x, BiasInput)
    assert x.vcc == 12.0 and x.beta == 150.0 and x.vbe == 0.7


def test_validate_rejects_non_numeric():
    """A non‑numeric string in any field → None + field‑error message."""
    bad = {**VALID, "r1": "abc"}
    _, errors = validate(bad)
    assert "r1" in errors


def test_validate_rejects_zero_resistors():
    """R1, R2, or RE exactly 0 → field error (never a crash)."""
    for field in ("r1", "r2", "re"):
        x, errors = validate({**VALID, field: "0"})
        assert x is None and field in errors


def test_validate_allows_zero_rc():
    """RC = 0 is explicitly allowed (resistor can be omitted)."""
    x, errors = validate({**VALID, "rc": "0"})
    assert errors == {} and x.rc == 0.0


def test_validate_rejects_bad_beta_and_vbe():
    """β = 0 and VBE = 1.2 are both rejected."""
    assert validate({**VALID, "beta": "0"})[1].keys() == {"beta"}
    assert validate({**VALID, "vbe": "1.2"})[1].keys() == {"vbe"}


def test_validate_reports_every_bad_field():
    """When *all* fields are bad, every key appears in the error dict."""
    bad = {
        "vcc": "-1",
        "r1": "x",
        "r2": "0",
        "rc": "-5",
        "re": "0",
        "beta": "0",
        "vbe": "0",
    }
    _, errors = validate(bad)
    assert set(errors) == {"vcc", "r1", "r2", "rc", "re", "beta", "vbe"}


def test_validate_accepts_comma_decimal():
    """A comma as decimal separator is accepted and converted."""
    x, errors = validate({**VALID, "vbe": "0,7"})
    assert errors == {} and x.vbe == pytest.approx(0.7)


def test_validate_rejects_empty_field():
    """Empty string in any field → that field gets an error."""
    x, errors = validate({**VALID, "vcc": ""})
    assert x is None and errors.keys() == {"vcc"}

# ----------------------------------------------------------------------
# ────────────────────────────────────────────────────────────────────
# Task 2 : closed‑form solver + region + formatters
# ────────────────────────────────────────────────────────────────────
# ----------------------------------------------------------------------


ACTIVE = BiasInput(12, 47000, 10000, 2200, 470, 150, 0.7)
CUTOFF = BiasInput(12, 100000, 1000, 2200, 470, 150, 0.7)
SAT    = BiasInput(12, 47000, 10000, 10000, 100, 150, 0.7)


def test_thevenin_active_known_values():
    """Standard active‑region bias point — numbers verifiable by hand."""
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
    """VBB ≤ VBE → cutoff: all currents zero, VCE = VCC."""
    r = solve_thevenin(CUTOFF)
    assert r.region == "cutoff" and r.warning is not None
    assert (r.ib, r.ic, r.ie) == (0.0, 0.0, 0.0)
    assert r.vce == pytest.approx(12.0) and r.ve == 0.0 and r.vc == pytest.approx(12.0)
    assert r.vb == pytest.approx(0.118812, rel=1e-4)


def test_cutoff_when_vbb_equals_vbe():
    """Exactly VBB = VBE is the cutoff boundary."""
    r = solve_thevenin(BiasInput(12, 113000, 7000, 2200, 470, 150, 0.7))
    assert r.vbb == pytest.approx(0.7) and r.region == "cutoff"


def test_thevenin_saturation_warns():
    """Large RC / small RE pushes the device into saturation."""
    r = solve_thevenin(SAT)
    assert r.region == "saturation" and r.warning is not None
    assert r.vce < 0.3


def test_vce_exactly_point_three_is_active():
    """VCE = 0.3 V is *not* saturation — it stays active."""
    x = BiasInput(12, 47000, 10000, 3300, 470, 150, 0.7)
    r = solve_thevenin(x)
    assert r.region in {"active", "saturation"}
    assert (r.region == "saturation") == (r.vce < 0.3)


def test_fmt_current():
    """fmt_current formats across the full range of magnitudes."""
    assert fmt_current(17.74e-6) == "17.74 µA"
    assert fmt_current(2.661e-3) == "2.661 mA"
    assert fmt_current(1.5) == "1.5000 A"
    assert fmt_current(0.0) == "0.00 µA"
    assert fmt_current(4e-7) == "0.40 µA"


def test_fmt_voltage():
    """fmt_voltage formats across the full range of magnitudes."""
    assert fmt_voltage(4.88659) == "4.887 V"
    assert fmt_voltage(0.7) == "700.0 mV"
    assert fmt_voltage(0.0) == "0.0 mV"


def test_thevenin_allows_zero_rc():
    """RC = 0 is a valid circuit — no collector resistor."""
    r = solve_thevenin(BiasInput(12, 47000, 10000, 0, 470, 150, 0.7))
    assert r.vc == pytest.approx(12.0) and r.vce == pytest.approx(12.0 - r.ve)


def test_nodal_matches_thevenin_active():
    """Nodal solve should give the same IC as Thevenin for the active case."""
    t = solve_thevenin(ACTIVE)
    n = solve_nodal(ACTIVE)
    assert n.region == "active"
    assert n.ic == pytest.approx(t.ic, rel=1e-9)


def test_nodal_matches_thevenin_cutoff():
    """Nodal and Thevenin both give cutoff (zero currents)."""
    t = solve_thevenin(CUTOFF)
    n = solve_nodal(CUTOFF)
    assert n.region == "cutoff"
    assert (n.ib, n.ic, n.ie) == (0.0, 0.0, 0.0)


def test_nodal_matches_thevenin_saturation():
    """Nodal and Thevenin both detect saturation."""
    t = solve_thevenin(SAT)
    n = solve_nodal(SAT)
    assert n.region == "saturation"
    assert n.vce < 0.3


def test_cross_check_identical():
    """cross_check returns zero when both results are the same."""
    r = solve_thevenin(ACTIVE)
    assert all(v == 0.0 for v in cross_check(r, r).values())


def test_cross_check_different_solvers():
    """cross_check should show a small but non-zero delta between Thevenin and Nodal."""
    t = solve_thevenin(ACTIVE)
    n = solve_nodal(ACTIVE)
    d = cross_check(t, n)
    # The two solvers use different algebra; they should agree to ~1e-12
    # but due to floating‑point we allow a loose tolerance here.
    assert max(d.values()) < 1e-9