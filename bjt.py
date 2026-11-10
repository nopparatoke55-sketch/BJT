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
    """Convert a form value to float, handling commas as decimal separators."""
    try:
        return float(raw.strip().replace(",", "."))
    except (ValueError, AttributeError):
        return None


def _error(field: str, msg: str) -> dict[str, str]:
    """Standard error dict returned to the caller."""
    return {field: msg}


def validate(raw: dict[str, str]) -> tuple[BiasInput | None, dict[str, str]]:
    """Validate all seven fields and return a :class:`BiasInput` on success."""
    parsed: dict[str, float] = {}
    errors: dict[str, str] = {}

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
        errors["r1"] = "R1 must be greater than 0 Ω."
    else:
        parsed["r1"] = v

    # r2
    v = _parse_float(raw.get("r2", ""), "r2")
    if v is None:
        errors["r2"] = "R2 must be a number."
    elif not (0 < v):
        errors["r2"] = "R2 must be greater than 0 Ω."
    else:
        parsed["r2"] = v

    # rc
    v = _parse_float(raw.get("rc", ""), "rc")
    if v is None:
        errors["rc"] = "RC must be a number."
    elif not (v >= 0):
        errors["rc"] = "RC must not be negative."
    else:
        parsed["rc"] = v

    # re
    v = _parse_float(raw.get("re", ""), "re")
    if v is None:
        errors["re"] = "RE must be a number."
    elif not (0 < v):
        errors["re"] = "RE must be greater than 0 Ω."
    else:
        parsed["re"] = v

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