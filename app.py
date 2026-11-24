"""Flask web app for the BJT Common-Emitter labs.

Lab 03 routes (``/`` and ``/calculate``) are preserved unchanged in behaviour.
Lab 04 adds ``/simulate``, which validates the CE reference-circuit form, runs
one real ngspice analysis (DC/AC/Transient) through :mod:`spice_engine` and
renders the parsed values and plots with provenance.

All engineering math still lives in :mod:`bjt` and :mod:`spice_engine`; this
module only reads the form, validates, dispatches and renders.
"""

from __future__ import annotations

import math

from flask import Flask, render_template, request

from bjt import (
    BIAS_MODES,
    BiasInput,
    validate,
    validate_mode,
    solve_fixed,
    solve_emitter,
    solve_thevenin,
    divider_display,
    fmt_current,
    fmt_voltage,
)
from charts import downsample, svg_line_chart
from spice_engine import (
    ANALYSIS_LABELS,
    ANALYSES,
    SIM_DEFAULTS,
    SpiceError,
    SpiceUnavailable,
    check_ngspice,
    run_simulation,
    validate_sim,
)

app = Flask(__name__)

# The form displays resistances in kΩ; convert to ohms exactly once here.
RESISTOR_SCALE = 1000.0

# Defaults are in kΩ and volts, matching the units printed on the form.
DEFAULTS = {
    "vcc": "12",
    "r1": "100",
    "r2": "22",
    "rc": "2.2",
    "re": "1",
    "rb": "1000",
    "beta": "100",
    "vbe": "0.7",
}

FIELDS = ("vcc", "r1", "r2", "rc", "re", "rb", "beta", "vbe")

MODE_LABELS = {
    "divider": "Voltage Divider Bias",
    "fixed": "Fixed Bias",
    "emitter": "Emitter Bias (single supply)",
}

CIRCUIT_FILES = {
    "divider": "circuit.svg",
    "fixed": "circuit-fixed.svg",
    "emitter": "circuit-emitter.svg",
}

CIRCUIT_NOTES = {
    "divider": "R1 and R2 set the base voltage; RC and RE set the operating point.",
    "fixed": "RB sets the base current; the emitter is tied directly to ground.",
    "emitter": "RB sets the base current; RE provides DC feedback and stabilises the bias.",
}

SIM_FIELDS = (
    "analysis",
    "vcc",
    "r1",
    "r2",
    "rc",
    "re",
    "rl",
    "cin",
    "cout",
    "amp_mv",
    "freq_hz",
    "ac_start_hz",
    "ac_stop_hz",
    "ac_points",
    "tstop_ms",
    "tstep_us",
    "beta_ref",
    "vbe_ref",
)


def _values_from(source) -> dict[str, str]:
    """Fill the whole form from *source*, falling back to per-field defaults."""
    return {field: source.get(field, DEFAULTS[field]) for field in FIELDS}


def _sim_values_from(source) -> dict[str, str]:
    """Fill the simulation form from *source*, falling back to defaults."""
    return {field: source.get(field, SIM_DEFAULTS[field]) for field in SIM_FIELDS}


def _render(
    mode: str,
    values: dict[str, str],
    result=None,
    errors=None,
    *,
    sim_values=None,
    sim_result=None,
    sim_error=None,
    sim_errors=None,
):
    """Render the single page with the current mode and values."""
    return render_template(
        "index.html",
        defaults=DEFAULTS,
        values=values,
        result=result,
        errors=errors or {},
        mode=mode,
        mode_label=MODE_LABELS[mode],
        circuit_file=CIRCUIT_FILES[mode],
        circuit_note=CIRCUIT_NOTES[mode],
        sim_defaults=SIM_DEFAULTS,
        sim_values=sim_values or dict(SIM_DEFAULTS),
        sim_result=sim_result,
        sim_error=sim_error,
        sim_errors=sim_errors or {},
        sim_status=check_ngspice(),
        analysis_labels=ANALYSIS_LABELS,
        analyses=ANALYSES,
    )


@app.route("/", methods=["GET"])
def index():
    """Display the calculator form, optionally reloaded for another mode."""
    mode = request.args.get("mode", "divider")
    if mode not in BIAS_MODES:
        mode = "divider"
    return _render(mode, _values_from(request.args))


@app.route("/calculate", methods=["POST"])
def calculate():
    """Handle form submission, validate, compute, and render results."""
    form = request.form.to_dict()
    mode = form.get("mode") or "divider"

    # An explicit unknown mode must never silently fall back to divider.
    if mode not in BIAS_MODES:
        return _render(
            "divider",
            _values_from(form),
            errors={"mode": "Unknown bias mode."},
        )

    if mode == "divider":
        model, errors = validate(form, RESISTOR_SCALE)
        result = divider_display(model) if model is not None else None
    elif mode == "fixed":
        model, errors = validate_mode(form, mode, RESISTOR_SCALE)
        result = solve_fixed(model) if model is not None else None
    else:  # emitter
        model, errors = validate_mode(form, mode, RESISTOR_SCALE)
        result = solve_emitter(model) if model is not None else None

    return _render(mode, _values_from(form), result=result, errors=errors)


# ---------------------------------------------------------------------------
# Lab 04 — SPICE simulation
# ---------------------------------------------------------------------------


def _delta(actual: float, reference: float, formatter) -> str:
    """Format the SPICE-minus-reference difference and relative error."""
    difference = actual - reference
    if reference:
        percent = f"{difference / reference * 100:+.1f}%"
    else:
        percent = "n/a"
    return f"{formatter(difference)} ({percent})"


def _fmt_freq(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return "not determined"
    if value >= 1e6:
        return f"{value / 1e6:.3g} MHz"
    if value >= 1e3:
        return f"{value / 1e3:.3g} kHz"
    return f"{value:.3g} Hz"


def _unwrap_phase(phases: list[float]) -> list[float]:
    """Unwrap a phase sequence so the Bode trace does not jump ±360°."""
    result: list[float] = []
    offset = 0.0
    previous: float | None = None
    for phase in phases:
        if previous is not None:
            while phase + offset - previous > 180:
                offset -= 360
            while phase + offset - previous < -180:
                offset += 360
        value = phase + offset
        result.append(value)
        previous = value
    return result


def _interp_log(f1: float, f2: float, y1: float, y2: float, target: float) -> float:
    """Linear interpolation in log-frequency space."""
    if f1 <= 0 or f2 <= 0 or f1 == f2 or y1 == y2:
        return f1
    fraction = (target - y1) / (y2 - y1)
    log_f = math.log10(f1) + fraction * (math.log10(f2) - math.log10(f1))
    return 10 ** log_f


def _cutoffs(freqs: list[float], gain_db: list[float]) -> dict[str, str]:
    """Return the −3 dB crossings only when the sweep actually contains them."""
    not_found = "not determined in sweep range"
    if len(gain_db) < 3:
        return {"low": not_found, "high": not_found, "level": "n/a"}
    peak_index = max(range(len(gain_db)), key=lambda index: gain_db[index])
    if peak_index in (0, len(gain_db) - 1):
        return {"low": not_found, "high": not_found, "level": "n/a"}
    level = gain_db[peak_index] - 3.0

    low = None
    for index in range(peak_index, 0, -1):
        a, b = gain_db[index - 1], gain_db[index]
        if (a - level) * (b - level) <= 0:
            low = _interp_log(freqs[index - 1], freqs[index], a, b, level)
            break

    high = None
    for index in range(peak_index, len(gain_db) - 1):
        a, b = gain_db[index], gain_db[index + 1]
        if (a - level) * (b - level) <= 0:
            high = _interp_log(freqs[index], freqs[index + 1], a, b, level)
            break

    return {
        "low": _fmt_freq(low) if low is not None else not_found,
        "high": _fmt_freq(high) if high is not None else not_found,
        "level": f"{level:.2f} dB",
    }


def _is_inverted(vin: list[float], vout: list[float]) -> bool | None:
    """Estimate phase inversion by the sign of the late-time correlation."""
    count = min(len(vin), len(vout))
    if count < 20:
        return None
    start = int(count * 0.4)
    a = vin[start:count]
    b = vout[start:count]
    mean_a = sum(a) / len(a)
    mean_b = sum(b) / len(b)
    numerator = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b))
    denom_a = math.sqrt(sum((x - mean_a) ** 2 for x in a))
    denom_b = math.sqrt(sum((y - mean_b) ** 2 for y in b))
    if denom_a == 0 or denom_b == 0:
        return None
    return numerator / (denom_a * denom_b) < -0.2


def _reference_beta_vbe(form: dict[str, str]) -> tuple[float, float]:
    """Read the analytical-reference β/VBE, falling back to documented values."""
    def read(field: str, default: float, low: float, high: float) -> float:
        try:
            value = float(str(form.get(field, "")).strip().replace(",", "."))
        except (TypeError, ValueError):
            return default
        if not math.isfinite(value) or not (low <= value <= high):
            return default
        return value

    return read("beta_ref", 100.0, 1.0, 10000.0), read("vbe_ref", 0.7, 0.1, 0.9)


def _build_sim_display(run, params, form: dict[str, str]) -> dict:
    """Turn a :class:`SimulationRun` into template-ready strings and SVGs."""
    display = {
        "analysis": run.analysis,
        "analysis_label": ANALYSIS_LABELS.get(run.analysis, run.analysis),
        "engine": run.engine,
        "version": run.ngspice_version,
        "model": run.model_name,
        "netlist": run.netlist,
        "log": run.log,
        "warnings": run.warnings,
    }

    if run.analysis == "dc":
        data = run.data
        beta_ref, vbe_ref = _reference_beta_vbe(form)
        reference = solve_thevenin(
            BiasInput(
                params.vcc,
                params.r1,
                params.r2,
                params.rc,
                params.re,
                beta_ref,
                vbe_ref,
            )
        )
        rows = [
            ("V<sub>B</sub>", data["vb"], reference.vb, fmt_voltage),
            ("V<sub>E</sub>", data["ve"], reference.ve, fmt_voltage),
            ("V<sub>C</sub>", data["vc"], reference.vc, fmt_voltage),
            ("V<sub>CE</sub>", data["vce"], reference.vce, fmt_voltage),
            ("I<sub>C</sub>", data["ic"], reference.ic, fmt_current),
            ("I<sub>B</sub>", data["ib"], reference.ib, fmt_current),
            ("I<sub>E</sub>", data["ie"], reference.ie, fmt_current),
        ]
        display["dc"] = {
            "rows": [
                {
                    "label": label,
                    "spice": formatter(actual),
                    "ref": formatter(expected),
                    "delta": _delta(actual, expected, formatter),
                }
                for label, actual, expected, formatter in rows
            ],
            "region": reference.region.upper(),
            "beta_ref": f"{beta_ref:g}",
            "vbe_ref": f"{vbe_ref:g}",
            "warning": reference.warning,
        }
    elif run.analysis == "ac":
        freqs = run.data["freq"]
        gains = run.data["gain"]
        phases = _unwrap_phase(run.data["phase"])
        gain_db = [
            20 * math.log10(gain) if gain > 0 else -300.0
            for gain in gains
        ]
        peak = max(range(len(gain_db)), key=lambda index: gain_db[index])
        display["ac"] = {
            "points": len(freqs),
            "max_gain_db": f"{gain_db[peak]:.2f} dB",
            "max_gain_freq": _fmt_freq(freqs[peak]),
            "phase_at_max": f"{phases[peak]:.1f}°",
            "cutoffs": _cutoffs(freqs, gain_db),
            "start": _fmt_freq(freqs[0]),
            "stop": _fmt_freq(freqs[-1]),
        }
        gain_points = downsample(list(zip(freqs, gain_db)))
        phase_points = downsample(list(zip(freqs, phases)))
        display["bode_gain_svg"] = svg_line_chart(
            [{"name": "|Vout/Vin|", "color": "#0d6efd", "points": gain_points}],
            x_label="Frequency (Hz)",
            y_label="Gain (dB)",
            title="AC gain — ngspice .ac",
            x_log=True,
        )
        display["bode_phase_svg"] = svg_line_chart(
            [{"name": "Phase of Vout/Vin", "color": "#6f42c1", "points": phase_points}],
            x_label="Frequency (Hz)",
            y_label="Phase (deg)",
            title="AC phase — ngspice .ac",
            x_log=True,
        )
    else:
        times = run.data["time"]
        vin = run.data["vin"]
        vout = run.data["vout"]
        count = min(len(times), len(vin), len(vout))
        times, vin, vout = times[:count], vin[:count], vout[:count]
        start = int(count * 0.4)
        window_in = vin[start:] or vin
        window_out = vout[start:] or vout
        vin_pp = max(window_in) - min(window_in)
        vout_pp = max(window_out) - min(window_out)
        gain = vout_pp / vin_pp if vin_pp else 0.0
        inverted = _is_inverted(vin, vout)
        display["tran"] = {
            "points": count,
            "vin_pp": f"{vin_pp * 1e3:.2f} mV",
            "vout_pp": fmt_voltage(vout_pp),
            "gain": f"{gain:.2f}×",
            "inverted": inverted,
            "duration": f"{(times[-1] - times[0]) * 1e3:.3f} ms",
        }
        time_ms = [value * 1e3 for value in times]
        display["tran_svg"] = svg_line_chart(
            [
                {"name": "Vin (source)", "color": "#20c997", "points": downsample(list(zip(time_ms, vin)))},
                {"name": "Vout", "color": "#fd7e14", "points": downsample(list(zip(time_ms, vout)))},
            ],
            x_label="Time (ms)",
            y_label="Voltage (V)",
            title="Transient — ngspice .tran",
        )

    return display


@app.route("/simulate", methods=["POST"])
def simulate():
    """Validate the CE form and run one real ngspice analysis."""
    form = request.form.to_dict()
    sim_values = _sim_values_from(form)
    params, sim_errors = validate_sim(form)

    if sim_errors:
        return _render(
            "divider",
            _values_from(form),
            sim_values=sim_values,
            sim_errors=sim_errors,
        )

    try:
        run = run_simulation(params)
    except SpiceUnavailable as exc:
        return _render(
            "divider",
            _values_from(form),
            sim_values=sim_values,
            sim_error={
                "kind": "unavailable",
                "message": str(exc),
                "netlist": exc.netlist,
                "log": exc.log,
            },
        )
    except SpiceError as exc:
        return _render(
            "divider",
            _values_from(form),
            sim_values=sim_values,
            sim_error={
                "kind": "error",
                "message": str(exc),
                "netlist": exc.netlist,
                "log": exc.log,
            },
        )

    return _render(
        "divider",
        _values_from(form),
        sim_values=sim_values,
        sim_result=_build_sim_display(run, params, form),
    )


if __name__ == "__main__":
    app.run(debug=True)
