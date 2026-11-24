"""ngspice adapter for the Lab 04 Common-Emitter amplifier.

The module has exactly four jobs:

1. validate the simulation form values (server side, per field),
2. turn one reference CE voltage-divider circuit into a SPICE netlist,
3. run ``ngspice`` in batch mode through :mod:`subprocess`, and
4. parse the ASCII data files written by the ``.control`` block.

It never invents a result.  If ngspice is missing, exits non-zero, times out,
or writes an empty/invalid file, the caller gets :class:`SpiceUnavailable` or
:class:`SpiceError` and the web layer must show an error instead of a graph.

Command-line options used by the app::

    ngspice -b -o run.log circuit.cir

The netlist carries a ``.control`` block with ``wrdata`` so the output is
plain whitespace-separated ASCII (much easier to audit than a binary rawfile).
The handout warns about mixing ``-b``/``-r`` with ``.control``; this adapter
never uses ``-r``, only ``-o`` for the log, and keeps every analysis directive
inside the control block.
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

#: Name of the generic small-signal NPN model used by the generated netlist.
#: The instructor-verified model can replace this card without touching the
#: parser or the web layer.
MODEL_NAME = "QNPN_GENERIC"
MODEL_CARD = (
    ".model QNPN_GENERIC NPN(IS=1e-14 BF=100 VAF=100 RB=10 RC=1 "
    "CJE=25p CJC=10p TF=0.4n TR=50n)"
)

OP_FILE = "op_data.txt"
AC_FILE = "ac_data.txt"
TRAN_FILE = "tran_data.txt"

DEFAULT_TIMEOUT = float(os.environ.get("SPICE_TIMEOUT", "20"))

#: Form defaults.  Resistances are kΩ, capacitors µF, amplitude mV (peak),
#: frequency Hz — the units printed on the form.
SIM_DEFAULTS = {
    "analysis": "dc",
    "vcc": "12",
    "r1": "100",
    "r2": "22",
    "rc": "2.2",
    "re": "1",
    "rl": "10",
    "cin": "10",
    "cout": "10",
    "amp_mv": "10",
    "freq_hz": "1000",
    "ac_start_hz": "1",
    "ac_stop_hz": "100000000",
    "ac_points": "20",
    "tstop_ms": "",
    "tstep_us": "",
    "beta_ref": "100",
    "vbe_ref": "0.7",
}

ANALYSES = ("dc", "ac", "tran")

ANALYSIS_LABELS = {
    "dc": "DC operating point (.op)",
    "ac": "AC frequency response (.ac)",
    "tran": "Transient response (.tran)",
}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class SpiceError(RuntimeError):
    """A real solver failure that must be shown to the user."""

    def __init__(self, message: str, *, log: str = "", netlist: str = ""):
        super().__init__(message)
        self.log = log or ""
        self.netlist = netlist or ""


class SpiceUnavailable(SpiceError):
    """The ngspice executable could not be found or started."""


# ---------------------------------------------------------------------------
# Parameters + validation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SimParams:
    analysis: str
    vcc: float          # V
    r1: float           # Ω
    r2: float           # Ω
    rc: float           # Ω
    re: float           # Ω
    rl: float           # Ω
    cin: float          # F
    cout: float         # F
    amp: float          # V peak
    freq: float         # Hz
    ac_start: float     # Hz
    ac_stop: float      # Hz
    ac_points: int      # points / decade
    tstep: float        # s
    tstop: float        # s


def _num(raw: dict[str, str], field: str) -> float | None:
    text = str(raw.get(field, "")).strip().replace(",", ".")
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _error(field: str, message: str) -> dict[str, str]:
    return {field: message}


def validate_sim(raw: dict[str, str]) -> tuple[SimParams | None, dict[str, str]]:
    """Validate the simulation form and return SI-unit :class:`SimParams`.

    Every message is attached to the field that caused it so the template can
    show it in place.  ``tstop_ms`` and ``tstep_us`` are optional; when blank
    they are derived from the source frequency (five cycles, 2 000 steps).
    """
    errors: dict[str, str] = {}

    analysis = str(raw.get("analysis", "dc")).strip().lower() or "dc"
    if analysis not in ANALYSES:
        errors["analysis"] = "Analysis must be DC, AC or Transient."

    vcc = _num(raw, "vcc")
    if vcc is None:
        errors["vcc"] = "VCC must be a number."
    elif not (0 < vcc <= 100):
        errors["vcc"] = "VCC must be between 0 and 100 V."

    def resistor(field: str, label: str, allow_zero: bool = False) -> float | None:
        value = _num(raw, field)
        if value is None:
            errors[field] = f"{label} must be a number."
            return None
        if allow_zero and value < 0:
            errors[field] = f"{label} must not be negative."
            return None
        if not allow_zero and value <= 0:
            errors[field] = f"{label} must be greater than 0 kΩ."
            return None
        return value * 1000.0

    r1 = resistor("r1", "R1")
    r2 = resistor("r2", "R2")
    rc = resistor("rc", "RC", allow_zero=True)
    re = resistor("re", "RE")
    rl = resistor("rl", "RL")

    def capacitor(field: str, label: str) -> float | None:
        value = _num(raw, field)
        if value is None:
            errors[field] = f"{label} must be a number."
            return None
        if value <= 0:
            errors[field] = f"{label} must be greater than 0 µF."
            return None
        return value * 1e-6

    cin = capacitor("cin", "Cin")
    cout = capacitor("cout", "Cout")

    amp_mv = _num(raw, "amp_mv")
    if amp_mv is None:
        errors["amp_mv"] = "Amplitude must be a number."
    elif not (0 < amp_mv <= 1000):
        errors["amp_mv"] = "Amplitude must be between 0 and 1000 mV peak."
    amp = amp_mv * 1e-3 if amp_mv is not None else None

    freq = _num(raw, "freq_hz")
    if freq is None:
        errors["freq_hz"] = "Frequency must be a number."
    elif not (0 < freq <= 1e9):
        errors["freq_hz"] = "Frequency must be between 0 and 1 GHz."

    ac_start = _num(raw, "ac_start_hz")
    if ac_start is None:
        ac_start = 1.0
    elif ac_start <= 0:
        errors["ac_start_hz"] = "AC start frequency must be greater than 0 Hz."

    ac_stop = _num(raw, "ac_stop_hz")
    if ac_stop is None:
        ac_stop = 1e8
    elif ac_stop <= 0:
        errors["ac_stop_hz"] = "AC stop frequency must be greater than 0 Hz."
    elif ac_start is not None and ac_stop <= ac_start:
        errors["ac_stop_hz"] = "AC stop frequency must be greater than the start frequency."

    ac_points_raw = _num(raw, "ac_points")
    if ac_points_raw is None:
        ac_points = 20
    elif not (1 <= ac_points_raw <= 1000):
        errors["ac_points"] = "Points per decade must be between 1 and 1000."
        ac_points = 20
    else:
        ac_points = int(ac_points_raw)

    tstop_ms = _num(raw, "tstop_ms")
    if "tstop_ms" in raw and str(raw.get("tstop_ms", "")).strip() and (tstop_ms is None or tstop_ms <= 0):
        errors["tstop_ms"] = "Stop time must be greater than 0 ms."
    if tstop_ms is None or tstop_ms <= 0:
        tstop = 5.0 / freq if freq and freq > 0 else 5e-3
    else:
        tstop = tstop_ms * 1e-3

    tstep_us = _num(raw, "tstep_us")
    if "tstep_us" in raw and str(raw.get("tstep_us", "")).strip() and (tstep_us is None or tstep_us <= 0):
        errors["tstep_us"] = "Time step must be greater than 0 µs."
    if tstep_us is None or tstep_us <= 0:
        tstep = tstop / 2000.0
    else:
        tstep = tstep_us * 1e-6

    if tstep <= 0 or tstop <= 0 or tstep >= tstop:
        errors["tstep_us"] = "Time step must be smaller than the stop time."

    if errors:
        return None, errors

    return (
        SimParams(
            analysis=analysis,
            vcc=float(vcc),
            r1=float(r1),
            r2=float(r2),
            rc=float(rc),
            re=float(re),
            rl=float(rl),
            cin=float(cin),
            cout=float(cout),
            amp=float(amp),
            freq=float(freq),
            ac_start=float(ac_start),
            ac_stop=float(ac_stop),
            ac_points=ac_points,
            tstep=float(tstep),
            tstop=float(tstop),
        ),
        {},
    )


# ---------------------------------------------------------------------------
# Netlist generation
# ---------------------------------------------------------------------------


def _g(value: float) -> str:
    """Format a float for a SPICE netlist without locale surprises."""
    return f"{value:.10g}"


def build_netlist(params: SimParams) -> str:
    """Return a readable, auditable netlist for the reference CE circuit.

    The circuit is the exact reference from the handout: VCC → R1/R2 divider,
    RC collector load, unbypassed RE, NPN Q1, Cin/Cout coupling and RL load.
    """
    lines = [
        "* Lab 04 - CE voltage-divider amplifier - generated by spice_engine.py",
        f"* model: {MODEL_NAME}",
        f"VCC vcc 0 DC {_g(params.vcc)}",
        f"R1 vcc base {_g(params.r1)}",
        f"R2 base 0 {_g(params.r2)}",
        f"RC vcc collector {_g(params.rc)}",
        f"RE emitter 0 {_g(params.re)}",
        f"Q1 collector base emitter {MODEL_NAME}",
        f"CIN source base {_g(params.cin)}",
        f"COUT collector out {_g(params.cout)}",
        f"RL out 0 {_g(params.rl)}",
        f"VIN source 0 DC 0 AC 1 SIN(0 {_g(params.amp)} {_g(params.freq)})",
        MODEL_CARD,
        "",
        ".control",
        "set wr_singlescale",
        "set wr_vecnames",
    ]

    if params.analysis == "dc":
        lines += [
            "op",
            # ngspice reports the NPN emitter current with the opposite sign
            # (current into the emitter terminal).  The UI shows magnitudes,
            # so make the convention explicit here instead of hiding it later.
            "let ic = abs(@q1[ic])",
            "let ib = abs(@q1[ib])",
            "let ie = abs(@q1[ie])",
            f"wrdata {OP_FILE} v(base) v(emitter) v(collector) ic ib ie",
        ]
    elif params.analysis == "ac":
        lines += [
            f"ac dec {params.ac_points} {_g(params.ac_start)} {_g(params.ac_stop)}",
            "let gain = mag(v(out)/v(source))",
            "let phase = ph(v(out)/v(source))*180/pi",
            f"wrdata {AC_FILE} gain phase",
        ]
    else:
        lines += [
            f"tran {_g(params.tstep)} {_g(params.tstop)}",
            f"wrdata {TRAN_FILE} v(source) v(out)",
        ]

    lines += [".endc", ".end", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# ngspice discovery + version
# ---------------------------------------------------------------------------


def find_ngspice(explicit: str | None = None) -> str | None:
    """Locate the ngspice executable, honouring ``NGSPICE_BIN``."""
    candidates: list[str] = []
    if explicit:
        candidates.append(explicit)
    env = os.environ.get("NGSPICE_BIN")
    if env:
        candidates.append(env)
    if os.name == "nt":
        # The Windows package ships a GUI executable and a console one;
        # prefer the console build for batch runs.
        candidates.extend(("ngspice_con", "ngspice"))
    else:
        candidates.append("ngspice")

    for candidate in candidates:
        found = shutil.which(candidate)
        if found:
            return found
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return os.path.abspath(candidate)

    # Common Windows install locations, used only as a last resort.
    if os.name == "nt":
        bases = [os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", "")]
        rels = (
            os.path.join("ngspice", "bin", "ngspice.exe"),
            os.path.join("ngspice", "bin", "ngspice_con.exe"),
            os.path.join("Spice64", "bin", "ngspice.exe"),
        )
        for base in bases:
            if not base:
                continue
            for rel in rels:
                path = os.path.join(base, rel)
                if os.path.isfile(path):
                    return path
    return None


@lru_cache(maxsize=8)
def _ngspice_version(exe: str) -> str:
    """Return a one-line version string, or ``unknown`` if it cannot be read."""
    for flag in ("-v", "--version"):
        try:
            proc = subprocess.run(
                [exe, flag],
                capture_output=True,
                text=True,
                timeout=8,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        text = (proc.stdout or "") + "\n" + (proc.stderr or "")
        for line in text.splitlines():
            if "ngspice" in line.lower():
                return line.strip().strip("*").strip()
    return "unknown"


def check_ngspice() -> dict:
    """Return engine availability/status for the UI badge."""
    exe = find_ngspice()
    if not exe:
        return {
            "available": False,
            "path": None,
            "version": None,
            "model": MODEL_NAME,
            "message": (
                "ngspice executable not found. Install ngspice and add it to PATH, "
                "or set the NGSPICE_BIN environment variable."
            ),
        }
    return {
        "available": True,
        "path": exe,
        "version": _ngspice_version(exe),
        "model": MODEL_NAME,
        "message": "ngspice is ready.",
    }


# ---------------------------------------------------------------------------
# ASCII output parsing
# ---------------------------------------------------------------------------


def _as_float(token: str) -> float | None:
    try:
        value = float(token)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _read_wrdata(path: str) -> tuple[list[str] | None, list[list[float | None]]]:
    """Read an ngspice ``wrdata`` file.

    ``set wr_vecnames`` normally writes a header line; ``set wr_singlescale``
    makes the first column the shared scale (frequency/time).  The parser
    keeps the header when present and falls back to positional columns when a
    different ngspice build omits it.
    """
    if not os.path.isfile(path):
        raise SpiceError(f"ngspice did not write {os.path.basename(path)}.")
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith(("*", "#"))
    ]
    if not lines:
        raise SpiceError(f"{os.path.basename(path)} is empty.")

    first = lines[0].split()
    header: list[str] | None = None
    body = lines
    if any(_as_float(token) is None for token in first):
        header = first
        body = lines[1:]

    rows: list[list[float | None]] = []
    for line in body:
        values = [_as_float(token) for token in line.split()]
        if values and any(value is not None for value in values):
            rows.append(values)
    if not rows:
        raise SpiceError(f"{os.path.basename(path)} has no numeric data rows.")
    return header, rows


def _col(header: list[str] | None, aliases: Iterable[str]) -> int | None:
    if not header:
        return None
    normalised = [h.lower().strip() for h in header]
    for alias in aliases:
        alias = alias.lower()
        for index, name in enumerate(normalised):
            if alias == name or alias in name:
                return index
    return None


def _value(row: list[float | None], index: int | None) -> float | None:
    if index is None or index >= len(row):
        return None
    return row[index]


def _series(rows: list[list[float | None]], index: int | None) -> list[float]:
    """Extract one finite column, tolerating short/non-numeric rows."""
    values: list[float] = []
    for row in rows:
        value = _value(row, index)
        if value is not None and math.isfinite(value):
            values.append(value)
    return values


def parse_op(path: str) -> dict[str, float]:
    """Parse a DC operating-point ``wrdata`` file."""
    header, rows = _read_wrdata(path)
    row = rows[0]

    named = {
        "vb": _col(header, ("v(base)", "base")),
        "ve": _col(header, ("v(emitter)", "emitter")),
        "vc": _col(header, ("v(collector)", "collector")),
        "ic": _col(header, ("@q1[ic]", "ic")),
        "ib": _col(header, ("@q1[ib]", "ib")),
        "ie": _col(header, ("@q1[ie]", "ie")),
    }

    if any(index is not None for index in named.values()):
        data = {key: _value(row, index) for key, index in named.items()}
    else:
        # Fallback: the netlist writes v(base), v(emitter), v(collector),
        # @q1[ic], @q1[ib], @q1[ie].  Some builds repeat a scale column.
        values = [value for value in row if value is not None]
        if len(values) >= 12:
            values = values[1::2]
        keys = ("vb", "ve", "vc", "ic", "ib", "ie")
        data = dict(zip(keys, values[:6]))

    missing = [key for key, value in data.items() if value is None]
    if missing:
        raise SpiceError(
            "DC output is missing " + ", ".join(missing) + ".",
            log=Path(path).read_text(encoding="utf-8", errors="replace"),
        )

    result = {key: float(value) for key, value in data.items()}
    result["vce"] = result["vc"] - result["ve"]
    return result


def parse_ac(path: str) -> dict[str, list[float]]:
    """Parse an AC ``wrdata`` file into frequency, gain magnitude and phase."""
    header, rows = _read_wrdata(path)

    f_idx = _col(header, ("frequency", "freq"))
    g_idx = _col(header, ("gain", "mag"))
    p_idx = _col(header, ("phase", "ph"))

    if f_idx is None and header is None:
        width = max(len(row) for row in rows)
        # ngspice commonly prepends a 0-based index when wr_vecnames is absent.
        indexed = width >= 4 and all(
            rows[i][0] is not None and abs(rows[i][0] - i) < 1e-9
            for i in range(min(3, len(rows)))
        )
        offset = 1 if indexed else 0
        f_idx, g_idx, p_idx = offset, offset + 1, offset + 2

    if f_idx is None or g_idx is None:
        raise SpiceError("AC output has no frequency/gain columns.")

    freqs: list[float] = []
    gains: list[float] = []
    phases: list[float] = []
    for row in rows:
        f = _value(row, f_idx)
        g = _value(row, g_idx)
        p = _value(row, p_idx) if p_idx is not None else 0.0
        if f is None or g is None or not (math.isfinite(f) and math.isfinite(g)):
            continue
        if f <= 0 or g < 0:
            continue
        freqs.append(f)
        gains.append(g)
        phases.append(p if p is not None and math.isfinite(p) else 0.0)

    if not freqs:
        raise SpiceError("AC output contained no usable rows.")

    order = sorted(range(len(freqs)), key=lambda i: freqs[i])
    return {
        "freq": [freqs[i] for i in order],
        "gain": [gains[i] for i in order],
        "phase": [phases[i] for i in order],
    }


def parse_tran(path: str) -> dict[str, list[float]]:
    """Parse a transient ``wrdata`` file into time, Vin and Vout."""
    header, rows = _read_wrdata(path)

    t_idx = _col(header, ("time",))
    in_idx = _col(header, ("v(source)", "source"))
    out_idx = _col(header, ("v(out)", "out"))

    if t_idx is None and header is None:
        width = max(len(row) for row in rows)
        indexed = width >= 4 and all(
            rows[i][0] is not None and abs(rows[i][0] - i) < 1e-9
            for i in range(min(3, len(rows)))
        )
        offset = 1 if indexed else 0
        t_idx, in_idx, out_idx = offset, offset + 1, offset + 2

    if t_idx is None or in_idx is None or out_idx is None:
        raise SpiceError("Transient output has no time/Vin/Vout columns.")

    times, vin, vout = [], [], []
    for row in rows:
        t = _value(row, t_idx)
        a = _value(row, in_idx)
        b = _value(row, out_idx)
        if t is None or a is None or b is None:
            continue
        if not (math.isfinite(t) and math.isfinite(a) and math.isfinite(b)):
            continue
        times.append(t)
        vin.append(a)
        vout.append(b)

    if not times:
        raise SpiceError("Transient output contained no usable rows.")

    return {"time": times, "vin": vin, "vout": vout}


# ---------------------------------------------------------------------------
# Simulation run
# ---------------------------------------------------------------------------


@dataclass
class SimulationRun:
    analysis: str
    engine: str
    ngspice_version: str
    model_name: str
    netlist: str
    log: str
    data: dict
    warnings: list[str]


def run_simulation(
    params: SimParams,
    *,
    ngspice_bin: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    keep_dir: bool = False,
) -> SimulationRun:
    """Run one analysis and return parsed, unit-aware data.

    Raises :class:`SpiceUnavailable` when the executable cannot be found and
    :class:`SpiceError` for every other solver failure.  A stale result is
    never returned.
    """
    netlist = build_netlist(params)
    exe = find_ngspice(ngspice_bin)
    if not exe:
        raise SpiceUnavailable(
            "ngspice executable not found. Install ngspice and add it to PATH, "
            "or set NGSPICE_BIN.",
            netlist=netlist,
        )

    workdir = tempfile.mkdtemp(prefix="bjt_spice_")
    try:
        circuit = os.path.join(workdir, "circuit.cir")
        log_path = os.path.join(workdir, "run.log")
        Path(circuit).write_text(netlist, encoding="utf-8")

        try:
            proc = subprocess.run(
                [exe, "-b", "-o", log_path, circuit],
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise SpiceError(
                f"ngspice timed out after {timeout:g} s.",
                netlist=netlist,
                log=str(exc),
            ) from exc
        except OSError as exc:
            raise SpiceUnavailable(f"Could not start ngspice: {exc}", netlist=netlist) from exc

        log_text = ""
        if os.path.isfile(log_path):
            log_text = Path(log_path).read_text(encoding="utf-8", errors="replace")
        log_text += "\n" + (proc.stdout or "") + "\n" + (proc.stderr or "")
        lower = log_text.lower()

        if proc.returncode != 0:
            raise SpiceError(
                f"ngspice exited with code {proc.returncode}.",
                netlist=netlist,
                log=log_text,
            )
        if "fatal error" in lower or "error on line" in lower:
            raise SpiceError(
                "ngspice reported an error while reading the netlist.",
                netlist=netlist,
                log=log_text,
            )

        try:
            if params.analysis == "dc":
                data = parse_op(os.path.join(workdir, OP_FILE))
            elif params.analysis == "ac":
                data = parse_ac(os.path.join(workdir, AC_FILE))
            else:
                data = parse_tran(os.path.join(workdir, TRAN_FILE))
        except SpiceError as exc:
            # Keep provenance on parser failures too, not only on process
            # failures.
            raise SpiceError(
                str(exc),
                netlist=netlist,
                log=exc.log or log_text,
            ) from exc

        return SimulationRun(
            analysis=params.analysis,
            engine="ngspice",
            ngspice_version=_ngspice_version(exe),
            model_name=MODEL_NAME,
            netlist=netlist,
            log=log_text.strip(),
            data=data,
            warnings=[],
        )
    finally:
        if not keep_dir:
            shutil.rmtree(workdir, ignore_errors=True)
