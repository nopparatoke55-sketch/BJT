"""Tests for the Flask BJT bias calculator app (new layout)."""

import pytest
from app import app


@pytest.fixture
def client():
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


FORM = {
    "vcc": "12",
    "r1": "100000",
    "r2": "22000",
    "rc": "2200",
    "re": "1000",
    "beta": "100",
    "vbe": "0.7",
}


def test_index_shows_form_with_defaults(client):
    """GET / returns 200 and shows form with default values."""
    r = client.get("/")
    assert r.status_code == 200
    body = r.data.decode()
    assert "V<sub>CC</sub>" in body or "Supply Voltage" in body
    assert b'value="100000"' in r.data


def test_valid_post_shows_results(client):
    """POST /calculate with valid data shows results and status 200."""
    r = client.post("/calculate", data=FORM)
    assert r.status_code == 200
    body = r.data.decode()
    assert "ACTIVE" in body.upper()
    assert "mA" in body


def test_results_table_shown(client):
    """Results table shows all seven quantities."""
    body = client.post("/calculate", data=FORM).data.decode()
    assert "DC Bias Results" in body
    assert "V<sub>B</sub>" in body
    assert "V<sub>E</sub>" in body
    assert "V<sub>C</sub>" in body
    assert "V<sub>CE</sub>" in body
    assert "I<sub>B</sub>" in body
    assert "I<sub>C</sub>" in body
    assert "I<sub>E</sub>" in body


def test_invalid_post_keeps_values_and_shows_error(client):
    """POST with bad input re-displays form with errors, status 200."""
    bad = {**FORM, "r1": "abc"}
    r = client.post("/calculate", data=bad)
    assert r.status_code == 200
    body = r.data.decode()
    assert 'value="abc"' in body
    assert "R<sub>1</sub>" in body or "Upper Divider" in body


def test_zero_resistor_is_not_a_server_error(client):
    """re=0 should give a field error, not a 500."""
    bad = {**FORM, "re": "0"}
    r = client.post("/calculate", data=bad)
    assert r.status_code == 200
    body = r.data.decode()
    assert 'value="0"' in body
    assert "R<sub>E</sub>" in body or "Emitter Resistor" in body


def test_cutoff_warning_is_shown(client):
    """Cutoff case shows warning in the results card."""
    bad = {**FORM, "r2": "1000"}  # Makes VBB < VBE
    r = client.post("/calculate", data=bad)
    assert r.status_code == 200
    body = r.data.decode()
    assert "cutoff" in body.lower()


def test_saturation_warning_is_shown(client):
    """Saturation case shows warning in the results card."""
    bad = {**FORM, "rc": "10000", "re": "100"}
    r = client.post("/calculate", data=bad)
    assert r.status_code == 200
    body = r.data.decode()
    assert "saturation" in body.lower()
