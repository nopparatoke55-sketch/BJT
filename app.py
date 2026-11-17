"""Flask web app for BJT Common-Emitter DC Bias calculator (Lab 03).

Three bias modes are supported: voltage divider (unchanged from Lab 02),
fixed bias and single-supply emitter bias. All engineering math lives in
:mod:`bjt`; this module only reads the form, validates, dispatches to the
correct solver and renders the result.
"""

from flask import Flask, render_template, request

from bjt import (
    BIAS_MODES,
    validate,
    validate_mode,
    solve_fixed,
    solve_emitter,
    divider_display,
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


def _values_from(source) -> dict[str, str]:
    """Fill the whole form from *source*, falling back to per-field defaults."""
    return {field: source.get(field, DEFAULTS[field]) for field in FIELDS}


def _render(mode: str, values: dict[str, str], result=None, errors=None):
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


if __name__ == "__main__":
    app.run(debug=True)
