"""Flask web app for BJT Common-Emitter DC Bias calculator.

This module provides the web interface for the DC bias calculation.
It imports from bjt.py for all math — no physics hardcoded here.
"""

from flask import Flask, render_template, request, jsonify
from bjt import (
    BiasInput,
    validate,
    solve_thevenin,
    solve_nodal,
    solve_stiff_divider,
    cross_check,
    fmt_current,
    fmt_voltage,
)

app = Flask(__name__)

# Default values matching the reference screenshot (in ohms)
DEFAULTS = {
    "vcc": "12",
    "r1": "100000",
    "r2": "22000",
    "rc": "2200",
    "re": "1000",
    "beta": "100",
    "vbe": "0.7",
}


@app.route("/", methods=["GET"])
def index():
    """Display the bias calculator form with default values."""
    return render_template(
        "index.html",
        defaults=DEFAULTS,
        result=None,
        errors={},
        values=DEFAULTS,
    )


@app.route("/calculate", methods=["POST"])
def calculate():
    """Handle form submission, validate, compute, and render results."""
    form = request.form.to_dict()

    # Validate all fields
    bias, errors = validate(form)
    if bias is None:
        # Re-display form with entered values and error messages
        return render_template(
            "index.html",
            defaults=DEFAULTS,
            result=None,
            errors=errors,
            values={key: form.get(key, "") for key in DEFAULTS},
        )

    # Compute using stiff divider (primary, matches lab hand calculation)
    # and exact Thevenin (independent cross-check)
    stiff_result = solve_stiff_divider(bias)
    thevenin_result = solve_thevenin(bias)
    delta = cross_check(stiff_result, thevenin_result)

    # Build display-ready result dict from stiff divider (matches screenshot)
    result = {
        "region": stiff_result.region.upper(),
        "ib_fmt": fmt_current(stiff_result.ib),
        "ic_fmt": fmt_current(stiff_result.ic),
        "ie_fmt": fmt_current(stiff_result.ie),
        "vb_fmt": fmt_voltage(stiff_result.vb),
        "vc_fmt": fmt_voltage(stiff_result.vc),
        "ve_fmt": fmt_voltage(stiff_result.ve),
        "vce_fmt": fmt_voltage(stiff_result.vce),
        "delta_ic": fmt_current(delta["ic"]),
        "ok": max(delta.values()) < 1e-9,
        "warning": stiff_result.warning,
    }

    # Re-use the form values that were submitted
    submitted_values = {key: form.get(key, "") for key in DEFAULTS}

    return render_template(
        "index.html",
        defaults=DEFAULTS,
        result=result,
        errors={},
        values=submitted_values,
    )


if __name__ == "__main__":
    app.run(debug=True)