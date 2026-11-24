"""Flask route tests for the Lab 04 ``/simulate`` endpoint.

The real solver is replaced with an in-memory :class:`SimulationRun` so these
tests cover the web/rendering contract without requiring ngspice.  The error
path is tested explicitly: a missing solver must never look like a success.
"""

from __future__ import annotations

import math

import pytest

import app as app_module
from app import app
from spice_engine import SIM_DEFAULTS, SimulationRun, SpiceUnavailable

SIM_FORM = dict(SIM_DEFAULTS)

READY_ENGINE = {
    "available": True,
    "path": "C:/fake/ngspice.exe",
    "version": "ngspice-42",
    "model": "QNPN_GENERIC",
    "message": "ngspice is ready.",
}


@pytest.fixture
def client(monkeypatch):
    app.config.update(TESTING=True)
    monkeypatch.setattr(app_module, "check_ngspice", lambda: dict(READY_ENGINE))
    with app.test_client() as test_client:
        yield test_client


def _run(analysis: str, data: dict) -> SimulationRun:
    return SimulationRun(
        analysis=analysis,
        engine="ngspice",
        ngspice_version="ngspice-42",
        model_name="QNPN_GENERIC",
        netlist="* generated netlist\nQ1 collector base emitter QNPN_GENERIC\n.end",
        log="ngspice batch run\nNo. of Data Rows : 1",
        data=data,
        warnings=[],
    )


def test_index_has_simulation_section(client):
    body = client.get("/").data.decode()
    assert "Lab 04" in body
    assert "SPICE Simulation" in body
    assert 'action="/simulate"' in body


def test_index_has_three_column_workbench_and_no_placeholder_plots(client):
    body = client.get("/").data.decode()
    assert "sim-workbench" in body
    assert "Circuit &amp; Parameters" in body
    assert "Simulation &amp; Plots" in body
    assert "Engineering Results" in body
    assert "plot-svg" not in body


def test_simulation_units_are_not_replaced_by_question_marks(client):
    body = client.get("/").data.decode()
    assert "kΩ" in body
    assert "µF" in body
    assert "µs" in body
    assert "?" not in body


def test_simulate_dc_success_shows_spice_and_reference(client, monkeypatch):
    fake = _run(
        "dc",
        {"vb": 1.9, "ve": 1.2, "vc": 6.1, "vce": 4.9, "ic": 0.0022, "ib": 2.2e-5, "ie": 0.00222},
    )
    monkeypatch.setattr(app_module, "run_simulation", lambda params: fake)
    response = client.post("/simulate", data=SIM_FORM)
    assert response.status_code == 200
    body = response.data.decode()
    assert "run completed" in body
    assert "2.200 mA" in body
    assert "QNPN_GENERIC" in body
    assert "Analytical reference" in body


def test_simulate_missing_engine_is_an_explicit_error(client, monkeypatch):
    def unavailable(params):
        raise SpiceUnavailable(
            "ngspice executable not found. Install ngspice and add it to PATH.",
            netlist="* netlist not run",
        )

    monkeypatch.setattr(app_module, "run_simulation", unavailable)
    response = client.post("/simulate", data=SIM_FORM)
    assert response.status_code == 200
    body = response.data.decode()
    assert "Simulation unavailable" in body
    assert "ngspice executable not found" in body
    assert "run completed" not in body
    assert "Generated netlist (not run)" in body


def test_simulate_invalid_input_does_not_call_solver(client, monkeypatch):
    called = {"value": False}

    def should_not_run(params):
        called["value"] = True
        raise AssertionError("solver must not run for invalid input")

    monkeypatch.setattr(app_module, "run_simulation", should_not_run)
    response = client.post("/simulate", data={**SIM_FORM, "re": "0"})
    assert response.status_code == 200
    body = response.data.decode()
    assert "RE must be greater than 0" in body
    assert called["value"] is False


def test_simulate_ac_renders_bode_charts(client, monkeypatch):
    fake = _run(
        "ac",
        {
            "freq": [10.0, 100.0, 1000.0, 10000.0, 100000.0],
            "gain": [0.5, 5.0, 50.0, 40.0, 5.0],
            "phase": [-170.0, -175.0, -180.0, -185.0, -190.0],
        },
    )
    monkeypatch.setattr(app_module, "run_simulation", lambda params: fake)
    body = client.post("/simulate", data={**SIM_FORM, "analysis": "ac"}).data.decode()
    assert "AC Frequency Response" in body
    assert body.count("plot-svg") >= 2
    assert "Peak gain" in body


def test_simulate_transient_renders_waveform_and_phase(client, monkeypatch):
    time = [index * 0.0005 for index in range(41)]
    vin = [0.01 * math.sin(2 * math.pi * 1000 * t) for t in time]
    vout = [5.0 - 0.5 * math.sin(2 * math.pi * 1000 * t) for t in time]
    fake = _run("tran", {"time": time, "vin": vin, "vout": vout})
    monkeypatch.setattr(app_module, "run_simulation", lambda params: fake)
    body = client.post("/simulate", data={**SIM_FORM, "analysis": "tran"}).data.decode()
    assert "Transient Response" in body
    assert "plot-svg" in body
    assert "inverted" in body
