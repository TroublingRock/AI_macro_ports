"""Port and cartridge cavity dimensional standards (inches).

Geometry source rules
---------------------
SAE J1926-1 / ISO 6149-1:
  Truncated ORB from chart: SF → R → Z° for L1 → short 45° → tap minor.

BSPP (ISO 1179-1):
  Flat-face seal on spotface. d1 = orifice (not tap). Thread blank uses BSPP
  tap-drill Ø; short 45° tip into that blank (not a funnel to the orifice).

Cartridge cavities:
  Series depths are face-absolute OEM totals; converted to from-SF print dims.
  Short capped leads keep cylindrical lands. Verify angles to OEM form-tool print.

  Toolpath math (helix, TNC, flute segments) is in gcode_generator.py and uses
  these chart sizes as targets via the same resolved steps as the preview.
"""

from __future__ import annotations

import json
import math
from copy import deepcopy
from pathlib import Path
from typing import Any

_MM = 1.0 / 25.4


# ---------------------------------------------------------------------------
# SAE J1926-1 — chart rows
# Columns match common industry tables (INSERTA / Fluidtech / EPCO):
#   dash, thread, A, B, C, D, E, F, G, H, major, tap_drill
# ---------------------------------------------------------------------------

_SAE_ROWS: list[tuple] = [
    # dash, thread, L1, B(full thrd), C, D(tap depth), E(L3 max), F(d5), G(d2), Z, major, tap
    # L1 from Parker SAE J1926-1 (mm→in); F/G/E/D/Z aligned with chart practice
    (2,  "5/16-24",   0.075, 0.390, 0.074, 0.468, 0.063, 0.358, 0.669, 12, 0.3125, 0.261),
    (3,  "3/8-24",    0.075, 0.390, 0.074, 0.468, 0.063, 0.421, 0.748, 12, 0.3750, 0.332),
    (4,  "7/16-20",   0.094, 0.454, 0.093, 0.547, 0.063, 0.488, 0.827, 12, 0.4375, 0.390),
    (5,  "1/2-20",    0.094, 0.454, 0.093, 0.547, 0.063, 0.551, 0.906, 12, 0.5000, 0.453),
    (6,  "9/16-18",   0.098, 0.500, 0.097, 0.609, 0.063, 0.614, 0.984, 12, 0.5625, 0.516),
    (8,  "3/4-16",    0.098, 0.562, 0.100, 0.688, 0.094, 0.811, 1.181, 15, 0.7500, 0.688),
    (10, "7/8-14",    0.098, 0.656, 0.100, 0.787, 0.094, 0.941, 1.339, 15, 0.8750, 0.812),
    (12, "1-1/16-12", 0.130, 0.750, 0.130, 0.906, 0.094, 1.150, 1.614, 15, 1.0625, 0.984),
    (14, "1-3/16-12", 0.130, 0.750, 0.130, 0.906, 0.094, 1.272, 1.772, 15, 1.1875, 1.109),
    (16, "1-5/16-12", 0.130, 0.750, 0.130, 0.906, 0.126, 1.398, 1.929, 15, 1.3125, 1.234),
    (20, "1-5/8-12",  0.130, 0.750, 0.132, 0.906, 0.126, 1.713, 2.283, 15, 1.6250, 1.547),
    (24, "1-7/8-12",  0.130, 0.750, 0.132, 0.906, 0.126, 1.961, 2.559, 15, 1.8750, 1.797),
    (32, "2-1/2-12",  0.130, 0.750, 0.132, 0.906, 0.126, 2.587, 3.465, 15, 2.5000, 2.422),
    # Extended (non Parker table) — keep prior shape with short L1-like lead
    (40, "3-12",      0.130, 0.750, 0.132, 1.250, 0.094, 3.088, 3.875, 15, 3.0000, 2.922),
    (48, "3-1/2-12",  0.130, 0.750, 0.132, 1.250, 0.094, 3.588, 4.438, 15, 3.5000, 3.422),
]


def _tpi_from_thread(thread: str) -> float:
    return float(thread.rsplit("-", 1)[-1])


def _build_sae(row: tuple) -> dict[str, Any]:
    """SAE J1926-1 / ISO 11926-1 truncated port (Parker table U18 / S23).

    Print dims are from the spotface floor. Shape:
      spotface wall + flat floor (L3) → convex R → Z° (from vertical, Ød5 at floor)
      for chart L1 → short 45° into minor → thread minor to tap depth.

    Chart L1 is the Z° depth (long face on the sheet). The 45° is a short tip
    after L1 — not the bulk of the angled zone.
    """
    dash, thread, l1, b, c, d, e, f, g, z_ang, major, tap = row
    tan_z = math.tan(math.radians(max(min(float(z_ang), 80.0), 0.5)))
    r_d5 = float(f) / 2.0
    r_tap = float(tap) / 2.0
    r_after_z = r_d5 - float(l1) * tan_z
    # Short 45° (from vertical) closes remaining radial into minor
    dz_45 = max(r_after_z - r_tap, 0.012)
    l1_45 = round(float(l1) + dz_45, 4)
    return {
        "source": "SAE J1926-1 / ISO 11926-1 (Parker port detail)",
        "depth_mode": "from_seal_face",
        "profile": "sae_j1926",
        "angle_ref": "from_vertical",
        "thread": thread,
        "tpi": _tpi_from_thread(thread),
        "major_dia": major,
        "minor_dia": tap,
        "spotface_dia": g,
        "spotface_depth": e,  # shop default applied later; chart L3/E is MAX
        "chart_spotface_max": e,
        "counterbore_dia": f,  # d5 — at spotface / Z° intersection
        "full_thread_min": b,
        "tap_drill_depth": d,
        "port_depth": d,
        "chamfer_angle": float(z_ang),
        "chamfer_dia": d,
        "l1": l1,
        "chart": {
            "L1": l1,
            "B": b,
            "C": c,
            "D": d,
            "E": e,
            "F": f,
            "G": g,
            "Z": z_ang,
            "d5": f,
            "d2": g,
        },
        "steps": [
            {
                "name": "Spotface",
                "dia": g,
                "from_face": 0.0,
                "angle": 90.0,
                "is_spotface": True,
                "fillet_r": 0.0,
            },
            {
                "name": "Z lead (d5)",
                "dia": f,  # Ød5 at theoretical floor intersection
                "from_face": round(float(l1), 4),  # chart L1 = end of Z°
                "angle": float(z_ang),  # Z° from VERTICAL
                "angle_ref": "from_vertical",
                "is_spotface": False,
                # SAE corner R0.1–0.2 mm ≈ 0.004–0.008; shop often 0.010
                "fillet_r": 0.010,
            },
            {
                "name": "45 to minor",
                "dia": tap,
                "from_face": l1_45,  # short 45° tip after L1
                "angle": 45.0,  # from vertical
                "angle_ref": "from_vertical",
                "is_spotface": False,
                "fillet_r": 0.0,
            },
            {
                "name": "Thread minor",
                "dia": tap,
                "from_face": d,
                "angle": 0.0,
                "is_spotface": False,
                "fillet_r": 0.0,
            },
        ],
        "extended": dash in (40, 48),
    }


SAE_J1926: dict[str, dict[str, Any]] = {
    f"SAE-{row[0]}": _build_sae(row) for row in _SAE_ROWS
}


# ---------------------------------------------------------------------------
# BSPP — ISO 1179-1 / DIN 3852-2 (mm chart → inches)
# Columns (ISO 1179-1 Table 1):
#   dash, G-size, TPI, d1_orifice_mm, d2_mm, d3_sfN_mm, d4_sfW_mm,
#   L1_sf_max_mm, L2_full_thread_mm, L3_tap_depth_mm, major_in
# Note: d1 is the orifice / through-passage — NOT the tap drill.
# Tap drills: common BSPP recommended sizes (mm).
# ---------------------------------------------------------------------------

_BSPP_TAP_DRILL_MM: dict[str, float] = {
    "G1/8": 8.8,
    "G1/4": 11.8,
    "G3/8": 15.25,
    "G1/2": 19.0,
    "G5/8": 21.0,
    "G3/4": 24.5,
    "G1": 30.75,
    "G1-1/4": 39.5,
    "G1-1/2": 45.25,
    "G2": 57.0,
}

_BSPP_ROWS: list[tuple] = [
    # dash, g_size,  tpi, d1_orif, d2,  d3N, d4W, L1sf, L2thrd, L3tap, major_in
    ("2B",  "G1/8",  28, 4.5,  9.8, 15.0, 17.2, 1.0,  8.5, 10.5, 0.383),
    ("4B",  "G1/4",  19, 7.5, 13.2, 20.0, 20.7, 1.5, 12.5, 15.5, 0.518),
    ("6B",  "G3/8",  19, 9.0, 16.7, 23.0, 24.5, 2.0, 12.5, 15.5, 0.656),
    ("8B",  "G1/2",  14, 14.0, 21.0, 28.0, 29.6, 2.5, 15.0, 19.0, 0.825),
    ("10B", "G5/8",  14, 16.0, 23.0, 30.0, 32.0, 2.5, 16.0, 20.0, 0.902),
    ("12B", "G3/4",  14, 18.0, 26.5, 33.0, 36.9, 2.5, 16.5, 20.5, 1.041),
    ("16B", "G1",    11, 23.0, 33.3, 41.0, 46.1, 2.5, 19.0, 24.0, 1.309),
    ("20B", "G1-1/4", 11, 30.0, 42.0, 51.0, 54.0, 2.5, 21.5, 26.5, 1.650),
    ("24B", "G1-1/2", 11, 36.0, 47.9, 56.0, 60.5, 2.5, 22.5, 27.5, 1.882),
    ("32B", "G2",    11, 47.0, 59.7, 69.0, 73.3, 3.0, 26.0, 31.0, 2.347),
]


def _in(mm: float) -> float:
    return round(mm * _MM, 4)


def _build_bspp(row: tuple) -> dict[str, Any]:
    """ISO 1179-1 flat-face BSPP port (Form E style seal on spotface).

    Shape: SF wall + flat seal floor → small lip R → short 45° into tap blank
    → cylindrical thread minor to L3. d1 orifice is NOT the thread bore.
    """
    dash, g_size, tpi, d1_orif, d2, _d3, d4w, l1_sf, l2_thrd, l3_tap, major = row
    sf_depth_max = _in(l1_sf)
    approach = _in(d2)  # chart d2 — near major / approach under face
    tap_mm = _BSPP_TAP_DRILL_MM.get(g_size, d2 - 1.5)
    tap = _in(tap_mm)
    # Short 45° from vertical: axial = radial from approach → tap
    radial = max((approach - tap) / 2.0, 0.012)
    # Cap tip so we never build a long SF→orifice funnel
    l_chamfer = round(min(radial, 0.060), 4)
    orifice = _in(d1_orif)
    return {
        "source": "ISO 1179-1 flat-face BSPP (mm→inch) + BSPP tap drills",
        "depth_mode": "from_seal_face",
        "profile": "bspp_flat",
        "angle_ref": "from_vertical",
        "thread": f"{g_size}-{tpi}",
        "bspp_size": g_size,
        "tpi": float(tpi),
        "major_dia": major,
        "minor_dia": tap,
        "orifice_dia": orifice,
        "spotface_dia": _in(d4w),
        "spotface_depth": sf_depth_max,
        "chart_spotface_max": sf_depth_max,
        "counterbore_dia": approach,
        "full_thread_min": _in(l2_thrd),
        "tap_drill_depth": _in(l3_tap),
        "port_depth": _in(l3_tap),
        "chamfer_angle": 45.0,
        "chamfer_dia": approach,
        "l1": l_chamfer,
        "chart": {
            "d1_orifice_mm": d1_orif,
            "d2_mm": d2,
            "d4W_mm": d4w,
            "tap_drill_mm": tap_mm,
            "L1_sf_max_mm": l1_sf,
            "L2_full_thrd_mm": l2_thrd,
            "L3_tap_mm": l3_tap,
        },
        "steps": [
            {
                "name": "Spotface",
                "dia": _in(d4w),
                "from_face": 0.0,
                "angle": 90.0,
                "is_spotface": True,
                "fillet_r": 0.0,
            },
            {
                "name": "45 into minor",
                "dia": tap,
                "from_face": l_chamfer,
                "angle": 45.0,
                "angle_ref": "from_vertical",
                "is_spotface": False,
                "fillet_r": 0.008,  # ISO W lip ≈ 0.1–0.2 mm
            },
            {
                "name": "Thread minor",
                "dia": tap,
                "from_face": _in(l3_tap),
                "angle": 0.0,
                "is_spotface": False,
                "fillet_r": 0.0,
            },
        ],
    }


BSPP: dict[str, dict[str, Any]] = {
    f"SAE-{row[0]}": _build_bspp(row) for row in _BSPP_ROWS
}


# ---------------------------------------------------------------------------
# Cartridge valve cavities — common Sun-style series
# Depths / threads from published series data; intermediate steps are typical
# industry sketches (verify to OEM print before cutting).
# ---------------------------------------------------------------------------

def _cart(
    *,
    thread: str,
    tpi: float,
    major: float,
    minor: float,
    spot_dia: float,
    spot_depth: float,
    depth: float,
    steps: list[dict[str, Any]],
    description: str,
    series: str,
) -> dict[str, Any]:
    """Build a cartridge cavity template.

    Authored step `depth` values are absolute from the locating / boss face
    (OEM series style). Convert to print `from_face` (= abs − spotface) so
    `get_cavity` stacking does not add SF twice.
    """
    norm: list[dict[str, Any]] = []
    for i, s in enumerate(steps):
        row = dict(s)
        is_sf = i == 0 or "spotface" in str(row.get("name", "")).lower()
        row["is_spotface"] = is_sf
        abs_z = float(row.get("depth", 0.0))
        if "from_face" not in row:
            if is_sf:
                row["from_face"] = 0.0
            else:
                # Published depth is face-absolute; print dims are from SF floor
                row["from_face"] = round(max(abs_z - float(spot_depth), 0.001), 4)
        row.pop("depth", None)
        # Short leads — keep cylindrical lands (OEM form tools are not full cones)
        if not is_sf:
            row.setdefault("max_lead", 0.070 if i == 1 else 0.080)
        row.setdefault("fillet_r", 0.010 if (not is_sf and i == 1) else 0.0)
        row.setdefault("angle_ref", "from_vertical")
        norm.append(row)
    seal_from_face = next(
        (float(s["from_face"]) for s in norm if not s.get("is_spotface")),
        depth * 0.45,
    )
    return {
        "source": f"Cartridge series {series} (industry / OEM-published depths & thread)",
        "depth_mode": "from_seal_face",
        "profile": "cartridge_steps",
        "angle_ref": "from_vertical",
        "thread": thread,
        "tpi": tpi,
        "major_dia": major,
        "minor_dia": minor,
        "spotface_dia": spot_dia,
        "spotface_depth": spot_depth,
        "chart_spotface_max": spot_depth,
        "full_thread_min": seal_from_face,
        "tap_drill_depth": min(depth * 0.55, depth - 0.100),
        "port_depth": depth,
        "step_count": max(len(norm) - 1, 1),
        "description": description + " — verify angles/lands to OEM print",
        "series": series,
        "steps": norm,
    }


CARTRIDGE: dict[str, dict[str, Any]] = {
    "C08-2": _cart(
        thread="3/4-16",
        tpi=16,
        major=0.750,
        minor=0.688,
        spot_dia=1.000,
        spot_depth=0.062,
        depth=1.156,
        series="T-8A / C08-2",
        description="3/4-16, 2-port, 3-step, depth 1.156\"",
        steps=[
            {"name": "Spotface / locating", "dia": 1.000, "depth": 0.062, "angle": 90.0, "chart_ref": "series"},
            {"name": "Step 1 (seal)", "dia": 0.687, "depth": 0.562, "angle": 15.0, "chart_ref": "series"},
            {"name": "Step 2", "dia": 0.562, "depth": 0.875, "angle": 45.0, "chart_ref": "series"},
            {"name": "Step 3 (nose)", "dia": 0.359, "depth": 1.156, "angle": 45.0, "chart_ref": "series"},
        ],
    ),
    "C08-3": _cart(
        thread="3/4-16",
        tpi=16,
        major=0.750,
        minor=0.688,
        spot_dia=1.000,
        spot_depth=0.062,
        depth=1.469,
        series="T-8A / C08-3",
        description="3/4-16, 3-port, depth 1.469\"",
        steps=[
            {"name": "Spotface / locating", "dia": 1.000, "depth": 0.062, "angle": 90.0, "chart_ref": "series"},
            {"name": "Step 1 (seal)", "dia": 0.687, "depth": 0.562, "angle": 15.0, "chart_ref": "series"},
            {"name": "Step 2", "dia": 0.562, "depth": 0.875, "angle": 45.0, "chart_ref": "series"},
            {"name": "Step 3", "dia": 0.484, "depth": 1.188, "angle": 45.0, "chart_ref": "series"},
            {"name": "Step 4 (nose)", "dia": 0.359, "depth": 1.469, "angle": 45.0, "chart_ref": "series"},
        ],
    ),
    "C10-2": _cart(
        thread="7/8-14",
        tpi=14,
        major=0.875,
        minor=0.812,
        spot_dia=1.125,
        spot_depth=0.062,
        depth=1.332,
        series="T-10A / C10-2",
        description="7/8-14, 2-port, depth 1.332\"",
        steps=[
            {"name": "Spotface / locating", "dia": 1.125, "depth": 0.062, "angle": 90.0, "chart_ref": "series"},
            {"name": "Step 1 (seal)", "dia": 0.797, "depth": 0.625, "angle": 15.0, "chart_ref": "series"},
            {"name": "Step 2", "dia": 0.687, "depth": 1.000, "angle": 45.0, "chart_ref": "series"},
            {"name": "Step 3 (nose)", "dia": 0.484, "depth": 1.332, "angle": 45.0, "chart_ref": "series"},
        ],
    ),
    "C10-3": _cart(
        thread="7/8-14",
        tpi=14,
        major=0.875,
        minor=0.812,
        spot_dia=1.125,
        spot_depth=0.062,
        depth=1.719,
        series="T-10A / C10-3",
        description="7/8-14, 3-port, depth 1.719\"",
        steps=[
            {"name": "Spotface / locating", "dia": 1.125, "depth": 0.062, "angle": 90.0, "chart_ref": "series"},
            {"name": "Step 1 (seal)", "dia": 0.797, "depth": 0.625, "angle": 15.0, "chart_ref": "series"},
            {"name": "Step 2", "dia": 0.687, "depth": 1.000, "angle": 45.0, "chart_ref": "series"},
            {"name": "Step 3", "dia": 0.562, "depth": 1.375, "angle": 45.0, "chart_ref": "series"},
            {"name": "Step 4 (nose)", "dia": 0.484, "depth": 1.719, "angle": 45.0, "chart_ref": "series"},
        ],
    ),
    "C12-2": _cart(
        thread="1-1/16-12",
        tpi=12,
        major=1.0625,
        minor=0.984,
        spot_dia=1.375,
        spot_depth=0.080,
        depth=1.625,
        series="T-13A / C12-2",
        description="1-1/16-12, 2-port, depth 1.625\"",
        steps=[
            {"name": "Spotface / locating", "dia": 1.375, "depth": 0.080, "angle": 90.0, "chart_ref": "series"},
            {"name": "Step 1 (seal)", "dia": 0.984, "depth": 0.750, "angle": 15.0, "chart_ref": "series"},
            {"name": "Step 2", "dia": 0.859, "depth": 1.188, "angle": 45.0, "chart_ref": "series"},
            {"name": "Step 3 (nose)", "dia": 0.609, "depth": 1.625, "angle": 45.0, "chart_ref": "series"},
        ],
    ),
    "C12-3": _cart(
        thread="1-1/16-12",
        tpi=12,
        major=1.0625,
        minor=0.984,
        spot_dia=1.375,
        spot_depth=0.080,
        depth=2.125,
        series="T-13A / C12-3",
        description="1-1/16-12, 3-port, depth 2.125\"",
        steps=[
            {"name": "Spotface / locating", "dia": 1.375, "depth": 0.080, "angle": 90.0, "chart_ref": "series"},
            {"name": "Step 1 (seal)", "dia": 0.984, "depth": 0.750, "angle": 15.0, "chart_ref": "series"},
            {"name": "Step 2", "dia": 0.859, "depth": 1.188, "angle": 45.0, "chart_ref": "series"},
            {"name": "Step 3", "dia": 0.734, "depth": 1.688, "angle": 45.0, "chart_ref": "series"},
            {"name": "Step 4 (nose)", "dia": 0.609, "depth": 2.125, "angle": 45.0, "chart_ref": "series"},
        ],
    ),
    "C12-4": _cart(
        thread="1-1/16-12",
        tpi=12,
        major=1.0625,
        minor=0.984,
        spot_dia=1.375,
        spot_depth=0.080,
        depth=2.625,
        series="T-13A / C12-4",
        description="1-1/16-12, 4-port, depth 2.625\"",
        steps=[
            {"name": "Spotface / locating", "dia": 1.375, "depth": 0.080, "angle": 90.0, "chart_ref": "series"},
            {"name": "Step 1 (seal)", "dia": 0.984, "depth": 0.750, "angle": 15.0, "chart_ref": "series"},
            {"name": "Step 2", "dia": 0.859, "depth": 1.188, "angle": 45.0, "chart_ref": "series"},
            {"name": "Step 3", "dia": 0.734, "depth": 1.688, "angle": 45.0, "chart_ref": "series"},
            {"name": "Step 4", "dia": 0.672, "depth": 2.188, "angle": 45.0, "chart_ref": "series"},
            {"name": "Step 5 (nose)", "dia": 0.609, "depth": 2.625, "angle": 45.0, "chart_ref": "series"},
        ],
    ),
    "C16-2": _cart(
        thread="1-5/16-12",
        tpi=12,
        major=1.3125,
        minor=1.234,
        spot_dia=1.625,
        spot_depth=0.100,
        depth=1.844,
        series="T-16A / C16-2",
        description="1-5/16-12, 2-port, depth 1.844\"",
        steps=[
            {"name": "Spotface / locating", "dia": 1.625, "depth": 0.100, "angle": 90.0, "chart_ref": "series"},
            {"name": "Step 1 (seal)", "dia": 1.187, "depth": 0.750, "angle": 15.0, "chart_ref": "series"},
            {"name": "Step 2", "dia": 1.062, "depth": 1.312, "angle": 45.0, "chart_ref": "series"},
            {"name": "Step 3 (nose)", "dia": 0.641, "depth": 1.844, "angle": 45.0, "chart_ref": "series"},
        ],
    ),
    "C16-3": _cart(
        thread="1-5/16-12",
        tpi=12,
        major=1.3125,
        minor=1.234,
        spot_dia=1.625,
        spot_depth=0.100,
        depth=2.875,
        series="T-16A / C16-3",
        description="1-5/16-12, 3-port, depth 2.875\"",
        steps=[
            {"name": "Spotface / locating", "dia": 1.625, "depth": 0.100, "angle": 90.0, "chart_ref": "series"},
            {"name": "Step 1 (seal)", "dia": 1.187, "depth": 0.750, "angle": 15.0, "chart_ref": "series"},
            {"name": "Step 2", "dia": 1.062, "depth": 1.500, "angle": 45.0, "chart_ref": "series"},
            {"name": "Step 3", "dia": 0.984, "depth": 2.188, "angle": 45.0, "chart_ref": "series"},
            {"name": "Step 4 (nose)", "dia": 0.641, "depth": 2.875, "angle": 45.0, "chart_ref": "series"},
        ],
    ),
    "C16-4": _cart(
        thread="1-5/16-12",
        tpi=12,
        major=1.3125,
        minor=1.234,
        spot_dia=1.625,
        spot_depth=0.100,
        depth=4.096,
        series="T-16A / C16-4",
        description="1-5/16-12, 4-port / 5-step, depth 4.096\"",
        steps=[
            {"name": "Spotface / locating", "dia": 1.625, "depth": 0.100, "angle": 90.0, "chart_ref": "series"},
            {"name": "Step 1 (seal)", "dia": 1.187, "depth": 0.750, "angle": 15.0, "chart_ref": "series"},
            {"name": "Step 2", "dia": 1.062, "depth": 1.500, "angle": 45.0, "chart_ref": "series"},
            {"name": "Step 3", "dia": 0.984, "depth": 2.375, "angle": 45.0, "chart_ref": "series"},
            {"name": "Step 4", "dia": 0.797, "depth": 3.250, "angle": 45.0, "chart_ref": "series"},
            {"name": "Step 5 (nose)", "dia": 0.641, "depth": 4.096, "angle": 45.0, "chart_ref": "series"},
        ],
    ),
    "C20-2": _cart(
        thread="1-5/8-12",
        tpi=12,
        major=1.625,
        minor=1.547,
        spot_dia=2.000,
        spot_depth=0.100,
        depth=2.125,
        series="T-18A / C20-2",
        description="1-5/8-12, 2-port, depth 2.125\"",
        steps=[
            {"name": "Spotface / locating", "dia": 2.000, "depth": 0.100, "angle": 90.0, "chart_ref": "series"},
            {"name": "Step 1 (seal)", "dia": 1.500, "depth": 0.875, "angle": 15.0, "chart_ref": "series"},
            {"name": "Step 2", "dia": 1.312, "depth": 1.500, "angle": 45.0, "chart_ref": "series"},
            {"name": "Step 3 (nose)", "dia": 0.875, "depth": 2.125, "angle": 45.0, "chart_ref": "series"},
        ],
    ),
    "C20-3": _cart(
        thread="1-5/8-12",
        tpi=12,
        major=1.625,
        minor=1.547,
        spot_dia=2.000,
        spot_depth=0.100,
        depth=3.250,
        series="T-18A / C20-3",
        description="1-5/8-12, 3-port, depth 3.250\"",
        steps=[
            {"name": "Spotface / locating", "dia": 2.000, "depth": 0.100, "angle": 90.0, "chart_ref": "series"},
            {"name": "Step 1 (seal)", "dia": 1.500, "depth": 0.875, "angle": 15.0, "chart_ref": "series"},
            {"name": "Step 2", "dia": 1.312, "depth": 1.625, "angle": 45.0, "chart_ref": "series"},
            {"name": "Step 3", "dia": 1.125, "depth": 2.438, "angle": 45.0, "chart_ref": "series"},
            {"name": "Step 4 (nose)", "dia": 0.875, "depth": 3.250, "angle": 45.0, "chart_ref": "series"},
        ],
    ),
    "C20-4": _cart(
        thread="1-5/8-12",
        tpi=12,
        major=1.625,
        minor=1.547,
        spot_dia=2.000,
        spot_depth=0.100,
        depth=4.500,
        series="T-18A / C20-4",
        description="1-5/8-12, 4-port, depth 4.500\"",
        steps=[
            {"name": "Spotface / locating", "dia": 2.000, "depth": 0.100, "angle": 90.0, "chart_ref": "series"},
            {"name": "Step 1 (seal)", "dia": 1.500, "depth": 0.875, "angle": 15.0, "chart_ref": "series"},
            {"name": "Step 2", "dia": 1.312, "depth": 1.750, "angle": 45.0, "chart_ref": "series"},
            {"name": "Step 3", "dia": 1.125, "depth": 2.625, "angle": 45.0, "chart_ref": "series"},
            {"name": "Step 4", "dia": 1.000, "depth": 3.500, "angle": 45.0, "chart_ref": "series"},
            {"name": "Step 5 (nose)", "dia": 0.875, "depth": 4.500, "angle": 45.0, "chart_ref": "series"},
        ],
    ),
}


# ---------------------------------------------------------------------------
# ISO 6149-1 — Metric straight-thread O-ring ports (DIN 3852-3 / SAE J2244)
# Chart values in millimetres; converted to inches for G20 toolpaths.
# Columns (ISO Table 1 / Parker ref):
#   d2 wide spotface, d3 narrow, d4 orifice ref, d_boss, d5 O-ring seat,
#   L_groove (O-ring CB depth), L2 tap depth, L3 spotface depth,
#   L4 full thread min, Z chamfer angle, tap drill (ISO 2306 approx)
# ---------------------------------------------------------------------------

_ISO6149_ROWS: list[tuple] = [
    # label, pitch_mm, d2, d3, d4, d_boss, d5, Lg, L2, L3, L4, Z, tap
    ("M8x1",    1.0, 17, 14, 3.0,  12.5,  9.1, 2.2, 11.5, 1.0, 10.0, 12, 7.0),
    ("M10x1",   1.0, 20, 16, 4.5,  14.5, 11.1, 2.2, 11.5, 1.0, 10.0, 12, 9.0),
    ("M12x1.5", 1.5, 23, 19, 6.0,  17.5, 13.8, 2.4, 14.0, 1.5, 11.5, 15, 10.5),
    ("M14x1.5", 1.5, 25, 21, 7.5,  19.5, 15.8, 2.4, 14.0, 1.5, 11.5, 15, 12.5),
    ("M16x1.5", 1.5, 28, 24, 9.0,  22.5, 17.8, 2.4, 15.5, 1.5, 13.0, 15, 14.5),
    ("M18x1.5", 1.5, 30, 26, 11.0, 24.5, 19.8, 2.4, 17.0, 2.0, 14.5, 15, 16.5),
    ("M20x1.5", 1.5, 33, 29, 12.0, 27.5, 21.8, 2.4, 17.0, 2.0, 14.5, 15, 18.5),  # cartridge-oriented in ISO
    ("M22x1.5", 1.5, 33, 29, 14.0, 27.5, 23.8, 2.4, 18.0, 2.0, 15.5, 15, 20.5),
    ("M27x2",   2.0, 40, 34, 18.0, 32.5, 29.4, 3.1, 22.0, 2.0, 19.0, 15, 25.0),
    ("M30x2",   2.0, 44, 38, 21.0, 36.5, 32.4, 3.1, 22.0, 2.0, 19.0, 15, 28.0),
    ("M33x2",   2.0, 49, 43, 23.0, 41.5, 35.4, 3.1, 22.0, 2.5, 19.0, 15, 31.0),
    ("M42x2",   2.0, 58, 52, 30.0, 50.5, 44.4, 3.1, 22.5, 2.5, 19.5, 15, 40.0),
    ("M48x2",   2.0, 63, 57, 36.0, 55.5, 50.4, 3.1, 25.0, 2.5, 22.0, 15, 46.0),
    ("M60x2",   2.0, 74, 67, 44.0, 65.5, 62.4, 3.1, 27.5, 2.5, 24.5, 15, 58.0),
]


def _build_iso6149(row: tuple) -> dict[str, Any]:
    """ISO 6149-1 truncated metric ORB — same cavity *shape* as SAE J1926-1.

    Columns: d2 SF wide, d3 SF narrow, d4 orifice ref, d_boss, d5 at Z∩floor,
    L1 (angled zone end), L2 tap depth, L3 SF depth, L4 full thread, Z°, tap.
    """
    label, pitch, d2, d3, d4, d_boss, d5, l1, l2, l3, l4, z, tap = row
    major_mm = float(label.split("x")[0][1:])
    pitch_in = pitch * _MM
    seat_dia = _in(d5)
    tap_dia = _in(tap)
    l1_in = _in(l1)
    tap_ff = _in(l2)
    return {
        "source": "ISO 6149-1 / DIN 3852-3 truncated housing (mm→inch)",
        "depth_mode": "from_seal_face",
        "profile": "sae_j1926",  # same truncated ORB form as SAE J1926-1
        "angle_ref": "from_vertical",
        "units_chart": "mm",
        "thread": label,
        "pitch_mm": pitch,
        "tpi": round(1.0 / pitch_in, 4),
        "major_dia": _in(major_mm),
        "minor_dia": tap_dia,
        "spotface_dia": _in(d2),
        "spotface_depth": _in(l3),
        "chart_spotface_max": _in(l3),
        "counterbore_dia": seat_dia,
        "full_thread_min": _in(l4),
        "tap_drill_depth": tap_ff,
        "port_depth": tap_ff,
        "chamfer_angle": float(z),
        "chamfer_dia": seat_dia,
        "l1": l1_in,
        "chart": {
            "d2_mm": d2,
            "d3_mm": d3,
            "d4_mm": d4,
            "d_boss_mm": d_boss,
            "d5_mm": d5,
            "L1_mm": l1,
            "L2_mm": l2,
            "L3_mm": l3,
            "L4_mm": l4,
            "Z_deg": z,
            "tap_mm": tap,
            "pitch_mm": pitch,
        },
        "steps": [
            {
                "name": "Spotface",
                "dia": _in(d2),
                "from_face": 0.0,
                "angle": 90.0,
                "is_spotface": True,
                "fillet_r": 0.0,
            },
            {
                "name": "Z lead (d5)",
                "dia": seat_dia,
                "from_face": round(l1_in, 4),  # chart L1 = end of Z°
                "angle": float(z),
                "angle_ref": "from_vertical",
                "is_spotface": False,
                "fillet_r": 0.010,
            },
            {
                "name": "45 to minor",
                "dia": tap_dia,
                "from_face": round(
                    l1_in
                    + max(
                        seat_dia / 2.0
                        - l1_in
                        * math.tan(math.radians(max(min(float(z), 80.0), 0.5)))
                        - tap_dia / 2.0,
                        0.012,
                    ),
                    4,
                ),
                "angle": 45.0,
                "angle_ref": "from_vertical",
                "is_spotface": False,
                "fillet_r": 0.0,
            },
            {
                "name": "Thread minor",
                "dia": tap_dia,
                "from_face": tap_ff,
                "angle": 0.0,
                "is_spotface": False,
                "fillet_r": 0.0,
            },
        ],
        "description": f"{label} metric O-ring port (ISO 6149-1)",
    }


ISO_6149: dict[str, dict[str, Any]] = {
    row[0]: _build_iso6149(row) for row in _ISO6149_ROWS
}


STANDARDS = {
    "SAE J1926-1": SAE_J1926,
    "BSPP": BSPP,
    "Metric ISO 6149-1": ISO_6149,
    "Cartridge Valve Cavities": CARTRIDGE,
}

# Shop practice: chart spotface depth (E / L3) is usually a MAX.
# Typical production spotface is shallower unless a print says otherwise.
SHOP_SPOTFACE_DEPTH = 0.030
_SHOP_SPOTFACE_STANDARDS = {"SAE J1926-1", "BSPP", "Metric ISO 6149-1"}

OVERRIDES_PATH = Path(__file__).resolve().parent / "port_overrides.json"
CUSTOM_STANDARDS_PATH = Path(__file__).resolve().parent / "custom_standards.json"

BUILTIN_NAMES = set(STANDARDS.keys())


def load_custom_standards() -> dict[str, dict[str, Any]]:
    if not CUSTOM_STANDARDS_PATH.exists():
        return {}
    try:
        with CUSTOM_STANDARDS_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_custom_standards(data: dict[str, dict[str, Any]]) -> None:
    with CUSTOM_STANDARDS_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def all_standards() -> dict[str, dict[str, Any]]:
    """Built-in charts + user-created standard sets."""
    merged = {k: v for k, v in STANDARDS.items()}
    for name, ports in load_custom_standards().items():
        if isinstance(ports, dict):
            merged[name] = ports
    return merged


def is_custom_standard(name: str) -> bool:
    return name not in BUILTIN_NAMES and name in load_custom_standards()


def list_standard_names() -> list[str]:
    return list(all_standards().keys())


def list_sizes(standard: str) -> list[str]:
    stds = all_standards()
    if standard not in stds:
        return []
    return list(stds[standard].keys())


def create_standard_set(name: str) -> tuple[bool, str]:
    name = name.strip()
    if not name:
        return False, "Enter a name for the standard set."
    if name in BUILTIN_NAMES:
        return False, f"'{name}' is a built-in standard and cannot be replaced."
    data = load_custom_standards()
    if name in data:
        return False, f"'{name}' already exists."
    data[name] = {}
    save_custom_standards(data)
    return True, f"Created standard set '{name}'."


def delete_standard_set(name: str) -> tuple[bool, str]:
    if name in BUILTIN_NAMES:
        return False, "Cannot delete a built-in standard."
    data = load_custom_standards()
    if name not in data:
        return False, "Standard set not found."
    del data[name]
    save_custom_standards(data)
    return True, f"Deleted '{name}'."


def _cavity_snapshot(cavity: dict[str, Any]) -> dict[str, Any]:
    """Face-referenced port definition suitable for custom standard storage."""
    snap: dict[str, Any] = {
        "source": cavity.get("source", "Custom shop standard"),
        "depth_mode": "from_seal_face",
        "thread": cavity.get("thread", ""),
        "tpi": float(cavity.get("tpi", 16)),
        "major_dia": float(cavity.get("major_dia", 0.0)),
        "minor_dia": float(cavity.get("minor_dia", 0.0)),
        "spotface_dia": float(cavity.get("spotface_dia", 0.0)),
        "spotface_depth": float(cavity.get("spotface_depth", SHOP_SPOTFACE_DEPTH)),
        "chart_spotface_max": float(
            cavity.get("chart_spotface_max", cavity.get("spotface_depth", SHOP_SPOTFACE_DEPTH))
        ),
        "counterbore_dia": float(cavity.get("counterbore_dia", 0.0)),
        "full_thread_min": float(cavity.get("full_thread_min", 0.0)),
        "tap_drill_depth": float(cavity.get("tap_drill_depth", 0.0)),
        "port_depth": float(cavity.get("port_depth", 0.0)),
        "chamfer_angle": float(cavity.get("chamfer_angle", 45.0)),
        "description": cavity.get("description", ""),
        "steps": [],
    }
    if cavity.get("pitch_mm") is not None:
        snap["pitch_mm"] = float(cavity["pitch_mm"])
    for step in cavity.get("steps", []):
        snap["steps"].append(
            {
                "name": step.get("name", ""),
                "dia": float(step.get("dia", 0.0)),
                "from_face": float(step.get("from_face", 0.0)),
                "angle": float(step.get("angle", 0.0)),
                "is_spotface": bool(step.get("is_spotface", False)),
                "fillet_r": float(step.get("fillet_r", 0.0)),
            }
        )
    return snap


def save_cavity_to_standard(
    set_name: str,
    size_name: str,
    cavity: dict[str, Any],
) -> tuple[bool, str]:
    set_name = set_name.strip()
    size_name = size_name.strip()
    if not set_name or not size_name:
        return False, "Standard set and size name are required."
    if set_name in BUILTIN_NAMES:
        return False, "Cannot write into a built-in standard. Create a custom set first."
    data = load_custom_standards()
    if set_name not in data:
        data[set_name] = {}
    data[set_name][size_name] = _cavity_snapshot(cavity)
    save_custom_standards(data)
    return True, f"Saved '{size_name}' into '{set_name}'."


def override_key(standard: str, size: str) -> str:
    return f"{standard}::{size}"


def load_overrides() -> dict[str, Any]:
    if not OVERRIDES_PATH.exists():
        return {}
    try:
        with OVERRIDES_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_overrides(data: dict[str, Any]) -> None:
    with OVERRIDES_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def has_override(standard: str, size: str) -> bool:
    return override_key(standard, size) in load_overrides()


def save_cavity_override(standard: str, size: str, cavity: dict[str, Any]) -> None:
    """Persist face-referenced shop profile for this port (survives restarts)."""
    payload = {
        "spotface_depth": float(cavity.get("spotface_depth", SHOP_SPOTFACE_DEPTH)),
        "spotface_dia": float(cavity.get("spotface_dia", 0.0)),
        "depth_mode": "from_seal_face",
        "steps": [],
    }
    for step in cavity.get("steps", []):
        payload["steps"].append(
            {
                "name": step.get("name", ""),
                "dia": float(step.get("dia", 0.0)),
                "from_face": float(step.get("from_face", 0.0)),
                "angle": float(step.get("angle", 0.0)),
                "is_spotface": bool(step.get("is_spotface", False)),
                "fillet_r": float(step.get("fillet_r", 0.0)),
            }
        )
    data = load_overrides()
    data[override_key(standard, size)] = payload
    save_overrides(data)


def clear_cavity_override(standard: str, size: str) -> None:
    data = load_overrides()
    data.pop(override_key(standard, size), None)
    save_overrides(data)


def _apply_override(cavity: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    if "spotface_depth" in override:
        cavity["spotface_depth"] = float(override["spotface_depth"])
    if "spotface_dia" in override:
        cavity["spotface_dia"] = float(override["spotface_dia"])
    cavity["depth_mode"] = "from_seal_face"
    if isinstance(override.get("steps"), list) and override["steps"]:
        cavity["steps"] = deepcopy(override["steps"])
    cavity["using_saved_profile"] = True
    return cavity


def absolute_step_depth(spotface_depth: float, step: dict[str, Any], depth_mode: str) -> float:
    """Print dims are FROM the spot/seal face. Whole profile moves with spotface depth.

      abs = spotface_depth + from_face   (spotface itself = spotface_depth)
    """
    del depth_mode  # unified stacking for all standards
    from_face = float(step.get("from_face", step.get("depth", 0.0)))
    is_sf = bool(step.get("is_spotface")) or "spotface" in str(step.get("name", "")).lower()
    if is_sf:
        return float(spotface_depth)
    return float(spotface_depth) + from_face


def resolve_cavity_steps(cavity: dict[str, Any]) -> list[dict[str, Any]]:
    """Return mill-ready steps with absolute `depth` for gcode_generator."""
    sf = float(cavity.get("spotface_depth", SHOP_SPOTFACE_DEPTH))
    mode = str(cavity.get("depth_mode", "from_seal_face"))
    out: list[dict[str, Any]] = []
    for step in cavity.get("steps", []):
        row = dict(step)
        row["depth"] = round(absolute_step_depth(sf, row, mode), 4)
        out.append(row)
    return out


def apply_resolved_depths(cavity: dict[str, Any]) -> dict[str, Any]:
    """Write absolute depths onto cavity for generation + port_depth sync."""
    resolved = resolve_cavity_steps(cavity)
    cavity["steps"] = resolved
    if resolved:
        cavity["port_depth"] = max(float(s["depth"]) for s in resolved)
        for s in resolved:
            if s.get("is_spotface"):
                cavity["spotface_dia"] = float(s["dia"])
                cavity["spotface_depth"] = float(s["depth"])
                break
    return cavity


def get_cavity(
    standard: str,
    size: str,
    *,
    shop_defaults: bool = True,
    use_override: bool = True,
) -> dict[str, Any]:
    stds = all_standards()
    if standard not in stds or size not in stds[standard]:
        raise KeyError(f"Unknown port {standard} / {size}")
    cavity = deepcopy(stds[standard][size])
    cavity["using_saved_profile"] = False
    cavity["depth_mode"] = "from_seal_face"
    if shop_defaults and standard in _SHOP_SPOTFACE_STANDARDS:
        cavity["spotface_depth"] = SHOP_SPOTFACE_DEPTH

    for i, step in enumerate(cavity.get("steps", [])):
        is_sf = bool(step.get("is_spotface")) or (
            i == 0 and "spotface" in str(step.get("name", "")).lower()
        )
        step["is_spotface"] = is_sf
        if "from_face" not in step:
            step["from_face"] = 0.0 if is_sf else float(step.get("depth", 0.0))
        step.pop("depth", None)

    if use_override:
        ov = load_overrides().get(override_key(standard, size))
        if ov:
            _apply_override(cavity, ov)

    return apply_resolved_depths(cavity)


def sync_port_depth_from_steps(cavity: dict[str, Any]) -> dict[str, Any]:
    return apply_resolved_depths(cavity)
