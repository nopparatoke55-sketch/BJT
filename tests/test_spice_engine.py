"""Tests for :mod:`spice_engine` — netlist, parsers and error paths.

These tests do not require ngspice to be installed.  The parser tests use
synthetic files in the documented ``wrdata`` layout, and the subprocess test
replaces the real solver with a stub that writes those files.  A real run is
still recorded separately in ``docs/validation.md``.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

import spice_engine as se
from spice_engine import (
    SIM_DEFAULTS,
    SimParams,
    SpiceError,
    SpiceUnavailable,
    build_netlist,
    parse_ac,
    parse_op,
    parse_tran,
    run_simulation,
    validate_sim,
)


def _params(analysis: str = "dc") -> SimParams:
    params, errors = validate_sim({**SIM_DEFAULTS, "analysis": analysis})
    assert errors == {}
    assert params is not None
    return params


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_defaults_validate():
    params, errors = validate_sim(SIM_DEFAULTS)
    assert errors == {}
    assert params.vcc == pytest.approx(12.0)
    assert params.r1 == pytest.approx(100_000)
    assert params.r2 == pytest.approx(22_000)
    assert params.rc == pytest.approx(2_200)
    assert params.re == pytest.approx(1_000)
    assert params.rl == pytest.approx(10_000)
    assert params.cin == pytest.approx(10e-6)
    assert params.amp == pytest.approx(10e-3)
    assert params.freq == pytest.approx(1_000)


def test_rejects_zero_and_negative_values():
    _, errors = validate_sim({**SIM_DEFAULTS, "re": "0", "vcc": "0", "amp_mv": "0"})
    assert {"re", "vcc", "amp_mv"} <= set(errors)


def test_rejects_bad_ac_range():
    _, errors = validate_sim({**SIM_DEFAULTS, "ac_start_hz": "1000", "ac_stop_hz": "100"})
    assert "ac_stop_hz" in errors


def test_rejects_unknown_analysis():
    _, errors = validate_sim({**SIM_DEFAULTS, "analysis": "bode"})
    assert "analysis" in errors


def test_transient_time_defaults_are_derived():
    params = _params("tran")
    assert params.tstop == pytest.approx(5.0 / 1000.0)
    assert 0 < params.tstep < params.tstop


# ---------------------------------------------------------------------------
# Netlist
# ---------------------------------------------------------------------------


def test_netlist_contains_reference_circuit_and_analysis():
    netlist = build_netlist(_params("dc"))
    for token in ("VCC", "R1 vcc base", "R2 base 0", "RC vcc collector", "RE emitter 0",
                  "Q1 collector base emitter", "CIN source base", "COUT collector out",
                  "RL out 0", "VIN source 0", "\nop\n", "wrdata op_data.txt", ".endc"):
        assert token in netlist
    assert se.MODEL_NAME in netlist


def test_netlist_uses_ac_and_tran_directives():
    ac = build_netlist(_params("ac"))
    assert "ac dec 20" in ac
    assert "wrdata ac_data.txt gain phase" in ac
    tran = build_netlist(_params("tran"))
    assert "tran " in tran
    assert "wrdata tran_data.txt v(source) v(out)" in tran


# ---------------------------------------------------------------------------
# Parsers (synthetic wrdata files)
# ---------------------------------------------------------------------------


def test_parse_op_maps_header_and_computes_vce(tmp_path: Path):
    path = tmp_path / "op.txt"
    path.write_text(
        "v(base) v(emitter) v(collector) @q1[ic] @q1[ib] @q1[ie]\n"
        "1.900 1.200 6.100 0.0022 2.2e-5 0.00222\n",
        encoding="utf-8",
    )
    data = parse_op(str(path))
    assert data["vb"] == pytest.approx(1.9)
    assert data["vce"] == pytest.approx(4.9)
    assert data["ic"] == pytest.approx(0.0022)


def test_parse_op_without_header_uses_positional_order(tmp_path: Path):
    path = tmp_path / "op.txt"
    path.write_text("1.9 1.2 6.1 0.0022 2.2e-5 0.00222\n", encoding="utf-8")
    data = parse_op(str(path))
    assert data["vb"] == pytest.approx(1.9)
    assert data["ie"] == pytest.approx(0.00222)


def test_parse_ac_sorts_by_frequency(tmp_path: Path):
    path = tmp_path / "ac.txt"
    path.write_text(
        "frequency gain phase\n"
        "1000 50 -180\n"
        "10 0.5 -170\n"
        "100 5 -175\n",
        encoding="utf-8",
    )
    data = parse_ac(str(path))
    assert data["freq"] == [10.0, 100.0, 1000.0]
    assert data["gain"] == [0.5, 5.0, 50.0]


def test_parse_tran_reads_three_columns(tmp_path: Path):
    path = tmp_path / "tran.txt"
    path.write_text(
        "time v(source) v(out)\n"
        "0 0 5\n"
        "0.001 0.01 6\n"
        "0.002 0 -1\n",
        encoding="utf-8",
    )
    data = parse_tran(str(path))
    assert data["time"] == [0.0, 0.001, 0.002]
    assert data["vin"][1] == pytest.approx(0.01)
    assert data["vout"][2] == pytest.approx(-1.0)


def test_missing_output_file_is_an_error(tmp_path: Path):
    with pytest.raises(SpiceError, match="did not write"):
        parse_op(str(tmp_path / "missing.txt"))


# ---------------------------------------------------------------------------
# Run orchestration (no real ngspice)
# ---------------------------------------------------------------------------


class _FakeCompleted:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _fake_subprocess(monkeypatch, *, write_data: bool = True, returncode: int = 0):
    def fake_run(cmd, **kwargs):
        if len(cmd) >= 2 and cmd[1] in ("-v", "--version"):
            return _FakeCompleted(stdout="ngspice-42\n")
        if "-b" in cmd:
            workdir = Path(kwargs["cwd"])
            circuit = Path(cmd[-1])
            text = circuit.read_text(encoding="utf-8")
            log_path = Path(cmd[cmd.index("-o") + 1])
            log_path.write_text("ngspice batch run\nNo. of Data Rows : 1\n", encoding="utf-8")
            if returncode == 0 and write_data:
                if "wrdata op_data.txt" in text:
                    (workdir / se.OP_FILE).write_text(
                        "v(base) v(emitter) v(collector) @q1[ic] @q1[ib] @q1[ie]\n"
                        "1.9 1.2 6.1 0.0022 2.2e-5 0.00222\n",
                        encoding="utf-8",
                    )
                elif "wrdata ac_data.txt" in text:
                    (workdir / se.AC_FILE).write_text(
                        "frequency gain phase\n10 0.5 -170\n100 5 -175\n1000 50 -180\n",
                        encoding="utf-8",
                    )
                elif "wrdata tran_data.txt" in text:
                    (workdir / se.TRAN_FILE).write_text(
                        "time v(source) v(out)\n0 0 5\n0.001 0.01 6\n0.002 0 -1\n",
                        encoding="utf-8",
                    )
            return _FakeCompleted(returncode=returncode)
        return _FakeCompleted(stdout="ngspice-42\n")

    monkeypatch.setattr(se.subprocess, "run", fake_run)
    monkeypatch.setattr(se, "find_ngspice", lambda *args, **kwargs: "fake-ngspice")
    se._ngspice_version.cache_clear()


def test_run_simulation_parses_fake_dc(monkeypatch):
    _fake_subprocess(monkeypatch)
    run = run_simulation(_params("dc"))
    assert run.analysis == "dc"
    assert run.engine == "ngspice"
    assert run.data["vce"] == pytest.approx(4.9)
    assert "ngspice-42" in run.ngspice_version


def test_run_simulation_raises_when_ngspice_missing(monkeypatch):
    monkeypatch.setattr(se, "find_ngspice", lambda *args, **kwargs: None)
    with pytest.raises(SpiceUnavailable, match="ngspice executable not found"):
        run_simulation(_params("dc"))


def test_run_simulation_raises_on_nonzero_exit(monkeypatch):
    _fake_subprocess(monkeypatch, returncode=1)
    with pytest.raises(SpiceError, match="exited with code 1"):
        run_simulation(_params("dc"))


def test_run_simulation_raises_when_output_missing(monkeypatch):
    _fake_subprocess(monkeypatch, write_data=False)
    with pytest.raises(SpiceError, match="did not write"):
        run_simulation(_params("dc"))


def test_run_simulation_parses_fake_ac_and_tran(monkeypatch):
    _fake_subprocess(monkeypatch)
    ac = run_simulation(_params("ac"))
    assert ac.data["freq"] == [10.0, 100.0, 1000.0]
    tran = run_simulation(_params("tran"))
    assert len(tran.data["time"]) == 3
