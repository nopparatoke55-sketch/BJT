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
    cross_check,
    fmt_current,
    fmt_voltage,
)

app = Flask(__name__)

# Default values shown on page load (values in ohms, matching the reference screenshot)
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

    # Compute using both independent methods
    thevenin_result = solve_thevenin(bias)
    nodal_result = solve_nodal(bias)
    delta = cross_check(thevenin_result, nodal_result)

    # Build display-ready result dict
    result = {
        "region": thevenin_result.region.upper(),
        "ib_fmt": fmt_current(thevenin_result.ib),
        "ic_fmt": fmt_current(thevenin_result.ic),
        "ie_fmt": fmt_current(thevenin_result.ie),
        "vb_fmt": fmt_voltage(thevenin_result.vb),
        "vc_fmt": fmt_voltage(thevenin_result.vc),
        "ve_fmt": fmt_voltage(thevenin_result.ve),
        "vce_fmt": fmt_voltage(thevenin_result.vce),
        "delta_ic": fmt_current(delta["ic"]),
        "ok": max(delta.values()) < 1e-9,
        "thevenin": thevenin_result,
        "nodal": nodal_result,
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