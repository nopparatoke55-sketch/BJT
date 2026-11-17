"""Pure-engineering math for BJT Common-Emitter DC Bias.

This module knows nothing about Flask; it only exposes:
  - `BiasInput`  — a frozen dataclass holding the seven design inputs.
  - `validate`   — server-side form validation, returns (BiasInput, {}) or (None, {field: message}).
  - `solve_thevenin` — closed-form Thevenin derivation (used by the app & the cross-check).
  - `solve_nodal`     — independent 2×2 nodal/KCL solve (cross-check partner).
  - `cross_check`     — compares two `BiasResult` objects, returns per-quantity deltas.
  - `fmt_current`, `fmt_voltage` — human‑readable formatting.

All region/cutoff/saturation logic lives inside this module as well.
"""

import math
from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class BiasInput:
    """Immutable container for the seven BJT bias parameters."""
    vcc: float
    r1: float
    r2: float
    rc: float
    re: float
    beta: float
    vbe: float


def _parse_float(raw: str, field: str) -> float | None:
    """Convert a form value to float, handling commas as decimal separators.

    Rejects values that are not finite (``nan``/``inf``) as required by Lab 03.
    """
    try:
        value = float(raw.strip().replace(",", "."))
    except (ValueError, AttributeError):
        return None
    if not math.isfinite(value):
        return None
    return value


def _error(field: str, msg: str) -> dict[str, str]:
    """Standard error dict returned to the caller."""
    return {field: msg}


def validate(raw: dict[str, str],
             resistor_scale: float = 1.0) -> tuple[BiasInput | None, dict[str, str]]:
    """Validate all seven fields and return a :class:`BiasInput` on success.

    ``resistor_scale`` converts the resistor fields to ohms before they enter
    :class:`BiasInput`. The web form uses kΩ, so it passes ``1000.0``; direct
    callers (and the Lab 02 tests) keep the default of 1.0 (ohms).
    """
    parsed: dict[str, float] = {}
    errors: dict[str, str] = {}
    unit = "kΩ" if resistor_scale != 1.0 else "Ω"

    # vcc
    v = _parse_float(raw.get("vcc", ""), "vcc")
    if v is None:
        errors["vcc"] = "VCC must be a number."
    elif not (0 < v <= 100):
        errors["vcc"] = "VCC must be between 0 and 100 V."
    else:
        parsed["vcc"] = v

    # r1
    v = _parse_float(raw.get("r1", ""), "r1")
    if v is None:
        errors["r1"] = "R1 must be a number."
    elif not (0 < v):
        errors["r1"] = f"R1 must be greater than 0 {unit}."
    else:
        parsed["r1"] = v * resistor_scale

    # r2
    v = _parse_float(raw.get("r2", ""), "r2")
    if v is None:
        errors["r2"] = "R2 must be a number."
    elif not (0 < v):
        errors["r2"] = f"R2 must be greater than 0 {unit}."
    else:
        parsed["r2"] = v * resistor_scale

    # rc
    v = _parse_float(raw.get("rc", ""), "rc")
    if v is None:
        errors["rc"] = "RC must be a number."
    elif not (v >= 0):
        errors["rc"] = "RC must not be negative."
    else:
        parsed["rc"] = v * resistor_scale

    # re
    v = _parse_float(raw.get("re", ""), "re")
    if v is None:
        errors["re"] = "RE must be a number."
    elif not (0 < v):
        errors["re"] = f"RE must be greater than 0 {unit}."
    else:
        parsed["re"] = v * resistor_scale

    # beta
    v = _parse_float(raw.get("beta", ""), "beta")
    if v is None:
        errors["beta"] = "β must be a number."
    elif not (0 < v):
        errors["beta"] = "β must be greater than 0."
    else:
        parsed["beta"] = v

    # vbe
    v = _parse_float(raw.get("vbe", ""), "vbe")
    if v is None:
        errors["vbe"] = "VBE must be a number."
    elif not (0 < v < 1):
        errors["vbe"] = "VBE must be between 0 and 1 V."
    else:
        parsed["vbe"] = v

    if errors:
        return None, errors

    vcc, r1, r2, rc, re, beta, vbe = (
        parsed["vcc"],
        parsed["r1"],
        parsed["r2"],
        parsed["rc"],
        parsed["re"],
        parsed["beta"],
        parsed["vbe"],
    )

    bias = BiasInput(vcc, r1, r2, rc, re, beta, vbe)
    return bias, {}


@dataclass(frozen=True)
class BiasResult:
    vbb: float
    rb: float
    ib: float
    ic: float
    ie: float
    vb: float
    vc: float
    ve: float
    vce: float
    region: str
    warning: str | None = None


def solve_thevenin(x: BiasInput) -> BiasResult:
    """Closed-form Thevenin bias point."""
    vcc, r1, r2, rc, re, beta, vbe = x.vcc, x.r1, x.r2, x.rc, x.re, x.beta, x.vbe

    vbb = vcc * r2 / (r1 + r2)
    rb  = r1 * r2 / (r1 + r2)
    ib  = (vbb - vbe) / (rb + (1 + beta) * re)
    ic  = beta * ib
    ie  = (1 + beta) * ib
    vb  = vbe + ie * re
    vc  = vcc - ic * rc
    ve  = ie * re
    vce = vc - ve

    if vbb <= vbe:
        result = BiasResult(
            vbb=vbb, rb=rb, ib=0.0, ic=0.0, ie=0.0,
            vb=vbb, vc=vcc, ve=0.0, vce=vcc,
            region="cutoff",
            warning="Transistor is in cutoff (VBB ≤ VBE); no collector current flows.",
        )
    elif vce < 0.3:
        result = BiasResult(
            vbb=vbb, rb=rb, ib=ib, ic=ic, ie=ie,
            vb=vb, vc=vc, ve=ve, vce=vce,
            region="saturation",
            warning="Transistor is in saturation (VCE < 0.3 V); the linear model no longer applies.",
        )
    else:
        result = BiasResult(
            vbb=vbb, rb=rb, ib=ib, ic=ic, ie=ie,
            vb=vb, vc=vc, ve=ve, vce=vce,
            region="active",
            warning=None,
        )

    return result


def solve_nodal(x: BiasInput) -> BiasResult:
    """Nodal (KCL) solve for the base‑emitter node.

    Unknowns:  VB  (base voltage)  and  IB  (base current).
    Two equations:
      (1) KCL at the base:   (VB − VCC)/R1 + (VB − VCC)/R2 + IB = 0
      (2) BE junction:       VB − VBE − IB · RE · (1+β) = 0
    After rearrangement into matrix form  A · [VB, IB]^T = B:
      A = [[1/R1 + 1/R2,   1     ],
           [1,            −(1+β)RE]]
      B = [VCC/R1,  VBE]
    The hand‑written 2×2 Gaussian elimination returns (VB, IB).
    """
    vcc, r1, r2, rc, re, beta, vbe = x.vcc, x.r1, x.r2, x.rc, x.re, x.beta, x.vbe

    vbb = vcc * r2 / (r1 + r2)
    rb  = r1 * r2 / (r1 + r2)

    # Conductance matrix entries
    G11 = 1.0 / r1 + 1.0 / r2   # coefficient of VB
    G12 = 1.0                    # coefficient of IB  (in first equation)
    G21 = 1.0                    # coefficient of VB  (in second equation)
    G22 = -(1.0 + beta) * re    # coefficient of IB  (in second equation)

    # Right‑hand side vector
    B1 = vcc / r1
    B2 = vbe

    # Determinant of the 2×2 system
    det = G11 * G22 - G12 * G21

    if abs(det) < 1e-15:
        raise ValueError("Singular nodal system — check resistor values")

    # Cramer's rule
    IB = (G11 * B2 - B1 * G21) / det
    VB = (B1 * G22 - G12 * B2) / det

    # Derived quantities (initially from nodal)
    IC = beta * IB
    IE = (1.0 + beta) * IB
    VC = vcc - IC * rc
    VE = IE * re
    VCE = VC - VE

    # ---- region classification (same as solve_thevenin) ----
    # Start with the nodal-computed values
    ib_val = IB
    ic_val = IC
    ie_val = IE
    vb_val = VB
    vc_val = VC
    ve_val = VE
    vce_val = VCE

    if vbb <= vbe:
        # Cutoff: force all currents to zero, adjust voltages
        region = "cutoff"
        ib_val = 0.0
        ic_val = 0.0
        ie_val = 0.0
        vb_val = vbb
        vc_val = vcc
        ve_val = 0.0
        vce_val = vcc
        warning = "Transistor is in cutoff (VBB ≤ VBE); no collector current flows."
    elif VCE < 0.3:
        # Saturation: keep computed currents, mark region
        region = "saturation"
        warning = "Transistor is in saturation (VCE < 0.3 V); the linear model no longer applies."
    else:
        # Active: keep all computed values
        region = "active"
        warning = None

    return BiasResult(
        vbb=vbb,
        rb=rb,
        ib=ib_val,
        ic=ic_val,
        ie=ie_val,
        vb=vb_val,
        vc=vc_val,
        ve=ve_val,
        vce=vce_val,
        region=region,
        warning=warning,
    )


def solve_stiff_divider(x: BiasInput) -> BiasResult:
    """Stiff divider approximation (approximate analysis).

    Assumes base current is negligible compared to divider current, so:
      VBB = VCC * R2 / (R1 + R2)   (ignoring IB loading)
      VE  = VBB - VBE
      IE  = VE / RE
      IC  = beta * IB,  IB = IE / (1 + beta)
      VC  = VCC - IC * RC
      VCE = VC - VE

    This matches the standard textbook “approximate analysis” used in ENG29 labs.
    """
    vcc, r1, r2, rc, re, beta, vbe = x.vcc, x.r1, x.r2, x.rc, x.re, x.beta, x.vbe

    vbb = vcc * r2 / (r1 + r2)
    rb = r1 * r2 / (r1 + r2)

    # Approximate: IB negligible through divider
    ve = vbb - vbe
    ie = ve / re
    ic = beta / (1.0 + beta) * ie   # IC = beta * IB, IB = IE/(1+beta)
    ib = ie / (1.0 + beta)

    vb = vbe + ie * re
    vc = vcc - ic * rc
    vce = vc - ve

    # Region classification (same rules)
    if vbb <= vbe:
        region = "cutoff"
        warning = "Transistor is in cutoff (VBB ≤ VBE); no collector current flows."
    elif vce < 0.3:
        region = "saturation"
        warning = "Transistor is in saturation (VCE < 0.3 V); the linear model no longer applies."
    else:
        region = "active"
        warning = None

    return BiasResult(
        vbb=vbb,
        rb=rb,
        ib=ib,
        ic=ic,
        ie=ie,
        vb=vb,
        vc=vc,
        ve=ve,
        vce=vce,
        region=region,
        warning=warning,
    )


def cross_check(a: BiasResult, b: BiasResult) -> dict[str, float]:
    """Return per‑quantity absolute differences between two results."""
    return {
        "ib": abs(a.ib - b.ib),
        "ic": abs(a.ic - b.ic),
        "ie": abs(a.ie - b.ie),
        "vb": abs(a.vb - b.vb),
        "vc": abs(a.vc - b.vc),
        "ve": abs(a.ve - b.ve),
        "vce": abs(a.vce - b.vce),
    }


def fmt_current(amperes: float) -> str:
    """Format a current value with the most convenient unit."""
    if abs(amperes) < 1e-3:
        return f"{amperes * 1e6:.2f} µA"
    if abs(amperes) < 1:
        return f"{amperes * 1e3:.3f} mA"
    return f"{amperes:.4f} A"


def fmt_voltage(volts: float) -> str:
    """Format a voltage value with the most convenient unit."""
    if abs(volts) < 1:
        return f"{volts * 1e3:.1f} mV"
    return f"{volts:.3f} V"


# ---------------------------------------------------------------------------
# Lab 03 additions: Fixed Bias and Emitter Bias (single supply)
# ---------------------------------------------------------------------------
# The Lab 02 divider functions above are deliberately left untouched so the
# voltage-divider result shown by the web app does not change.

BIAS_MODES = ("divider", "fixed", "emitter")


@dataclass(frozen=True)
class FixedInput:
    """Inputs for a fixed-bias common-emitter stage (emitter at ground)."""
    vcc: float
    rc: float
    rb: float
    beta: float
    vbe: float


@dataclass(frozen=True)
class EmitterInput:
    """Inputs for a single-supply emitter-bias common-emitter stage."""
    vcc: float
    rc: float
    rb: float
    re: float
    beta: float
    vbe: float


def _parse_common_inputs(raw: dict[str, str], errors: dict[str, str],
                         resistor_scale: float = 1.0) -> dict[str, float]:
    """Parse the four inputs shared by every bias mode (VCC, RC, β, VBE).

    ``resistor_scale`` is applied only to RC (in kΩ on the web form).
    """
    parsed: dict[str, float] = {}

    vcc = _parse_float(raw.get("vcc", ""), "vcc")
    if vcc is None:
        errors["vcc"] = "VCC must be a number."
    elif not (0 < vcc <= 100):
        errors["vcc"] = "VCC must be between 0 and 100 V."
    else:
        parsed["vcc"] = vcc

    rc = _parse_float(raw.get("rc", ""), "rc")
    if rc is None:
        errors["rc"] = "RC must be a number."
    elif not (rc >= 0):
        errors["rc"] = "RC must not be negative."
    else:
        parsed["rc"] = rc * resistor_scale

    beta = _parse_float(raw.get("beta", ""), "beta")
    if beta is None:
        errors["beta"] = "β must be a number."
    elif not (0 < beta):
        errors["beta"] = "β must be greater than 0."
    else:
        parsed["beta"] = beta

    vbe = _parse_float(raw.get("vbe", ""), "vbe")
    if vbe is None:
        errors["vbe"] = "VBE must be a number."
    elif not (0 < vbe < 1):
        errors["vbe"] = "VBE must be between 0 and 1 V."
    else:
        parsed["vbe"] = vbe

    return parsed


def _parse_resistor(raw: dict[str, str], field: str, label: str,
                    errors: dict[str, str],
                    resistor_scale: float = 1.0) -> float | None:
    """Parse a resistor that must be strictly positive, then convert to Ω."""
    value = _parse_float(raw.get(field, ""), field)
    if value is None:
        errors[field] = f"{label} must be a number."
        return None
    if not (0 < value):
        errors[field] = f"{label} must be greater than 0 Ω."
        return None
    return value * resistor_scale


def validate_mode(raw: dict[str, str], mode: str,
                  resistor_scale: float = 1.0):
    """Validate the form for *mode* and return a mode-specific input object.

    ``divider`` delegates to the untouched Lab 02 :func:`validate`, so its
    behaviour and error messages stay identical. Returns ``(model, errors)``;
    ``model`` is ``None`` whenever ``errors`` is non-empty. ``resistor_scale``
    converts the resistor fields from kΩ to Ω for the web form.
    """
    if mode == "divider":
        return validate(raw, resistor_scale)

    if mode not in ("fixed", "emitter"):
        return None, {"mode": "Unknown bias mode."}

    errors: dict[str, str] = {}
    parsed = _parse_common_inputs(raw, errors, resistor_scale)

    rb = _parse_resistor(raw, "rb", "RB", errors, resistor_scale)
    re = (_parse_resistor(raw, "re", "RE", errors, resistor_scale)
          if mode == "emitter" else None)

    if errors:
        return None, errors

    if mode == "fixed":
        return FixedInput(parsed["vcc"], parsed["rc"], rb,
                          parsed["beta"], parsed["vbe"]), {}
    return EmitterInput(parsed["vcc"], parsed["rc"], rb, re,
                        parsed["beta"], parsed["vbe"]), {}


def _display_result(mode: str, *, ib: float, ic: float, ie: float,
                    vb: float, vc: float, ve: float, vce: float,
                    region: str, warning: str | None) -> dict:
    """Build the shared result contract used by all three bias modes.

    Raw values keep SI units (A and V); the ``*_fmt`` strings are what the
    template displays, and ``ic_ma`` exposes IC directly in milliamps.
    """
    return {
        "mode": mode,
        "ib_a": ib,
        "ic_a": ic,
        "ie_a": ie,
        "ic_ma": ic * 1e3,
        "vb_v": vb,
        "vc_v": vc,
        "ve_v": ve,
        "vce_v": vce,
        "ib_fmt": fmt_current(ib),
        "ic_fmt": fmt_current(ic),
        "ic_ma_fmt": f"{ic * 1e3:.3f} mA",
        "ie_fmt": fmt_current(ie),
        "vb_fmt": fmt_voltage(vb),
        "vc_fmt": fmt_voltage(vc),
        "ve_fmt": fmt_voltage(ve),
        "vce_fmt": fmt_voltage(vce),
        "region": region.upper(),
        "warning": warning,
    }


def _classify_new_mode(ib: float, vce: float) -> tuple[str, str | None]:
    """Region rule for the new modes: warn if IB ≤ 0 or VCE ≤ 0.2 V."""
    if ib <= 0:
        return ("cutoff",
                "Forward-active model may not apply (IB ≤ 0); "
                "no collector current flows.")
    if vce <= 0.2:
        return ("saturation",
                "Forward-active model may not apply (VCE ≤ 0.2 V); "
                "the transistor may be saturated.")
    return "active", None


def solve_fixed(x: FixedInput) -> dict:
    """Solve the fixed-bias operating point (emitter tied to ground)."""
    ib = (x.vcc - x.vbe) / x.rb
    ic = x.beta * ib
    ie = (x.beta + 1.0) * ib
    ve = 0.0
    vb = x.vbe
    vc = x.vcc - ic * x.rc
    vce = vc - ve

    region, warning = _classify_new_mode(ib, vce)
    if region == "cutoff":
        ib = ic = ie = 0.0
        ve = 0.0
        vb, vc, vce = x.vcc, x.vcc, x.vcc

    return _display_result("fixed", ib=ib, ic=ic, ie=ie, vb=vb, vc=vc,
                           ve=ve, vce=vce, region=region, warning=warning)


def solve_emitter(x: EmitterInput) -> dict:
    """Solve the single-supply emitter-bias operating point."""
    ib = (x.vcc - x.vbe) / (x.rb + (x.beta + 1.0) * x.re)
    ic = x.beta * ib
    ie = (x.beta + 1.0) * ib
    ve = ie * x.re
    vb = ve + x.vbe
    vc = x.vcc - ic * x.rc
    vce = vc - ve

    region, warning = _classify_new_mode(ib, vce)
    if region == "cutoff":
        ib = ic = ie = 0.0
        ve = 0.0
        vb, vc, vce = x.vcc, x.vcc, x.vcc

    return _display_result("emitter", ib=ib, ic=ic, ie=ie, vb=vb, vc=vc,
                           ve=ve, vce=vce, region=region, warning=warning)


def divider_display(x: BiasInput) -> dict:
    """Return the shared display dict for the unchanged Lab 02 divider path."""
    stiff = solve_stiff_divider(x)
    exact = solve_thevenin(x)
    delta = cross_check(stiff, exact)

    result = _display_result(
        "divider",
        ib=stiff.ib, ic=stiff.ic, ie=stiff.ie,
        vb=stiff.vb, vc=stiff.vc, ve=stiff.ve, vce=stiff.vce,
        region=stiff.region, warning=stiff.warning,
    )
    result["delta_ic"] = fmt_current(delta["ic"])
    result["ok"] = max(delta.values()) < 1e-9
    return result