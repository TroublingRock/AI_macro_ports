"""Fanuc-style G-code generation for hydraulic ports & cartridge cavities."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Optional

STOCK_ALLOWANCE = 0.005  # wall stock left during roughing
BOTTOM_CLEARANCE = 0.030  # pilot drill short of floor
FLUTE_SEGMENT_RATIO = 0.80  # max Z per helix segment vs flute length
WEAR_OFFSET_VAR = "#501"  # Fanuc wear offset for EM diameter trim
TM_WEAR_OFFSET_VAR = "#502"  # Fanuc wear offset for threadmill diameter trim
HELIX_PITCH = 0.050  # Z rise per revolution during helix
SAFE_Z = 0.100
RAPID_Z = 1.000
# Profile surface finish: arc-length step along wall (inch) for seal/angle/radius
SURFACE_WALL_STEP = 0.002
# Spotface floor facing (EM bottom): shallow DOC + aggressive radial stepover
SPOTFACE_MAX_DOC = 0.030
SPOTFACE_STEPOVER_RATIO = 0.90  # fraction of EM diameter per outward spiral ring


def _f(val: float, digits: int = 4) -> str:
    return f"{val:.{digits}f}"


def _g03_two_semis(
    lines: list[str],
    r_pos: str,
    r_neg: str,
    feed: float,
    *,
    z_mid: Optional[float] = None,
    z_end: Optional[float] = None,
    use_brackets: bool = True,
) -> None:
    """Emit one full revolution as two 180° G03 semi-arcs.

    This control cannot interpolate a full 360° circle in a single block.
    Path: +X → −X (first semi), then −X → +X (second semi). I/J are
    incremental to center (origin) from each start point.
    """
    if use_brackets:
        x_neg, x_pos = f"X[{r_neg}]", f"X[{r_pos}]"
        i_neg, i_pos = f"I[{r_neg}]", f"I[{r_pos}]"
    else:
        x_neg, x_pos = f"X{r_neg}", f"X{r_pos}"
        i_neg, i_pos = f"I{r_neg}", f"I{r_pos}"
    z1 = f" Z{_f(z_mid)}" if z_mid is not None else ""
    z2 = f" Z{_f(z_end)}" if z_end is not None else ""
    lines.append(f"G03 {x_neg} Y0.{z1} {i_neg} J0. F{_f(feed, 2)}")
    lines.append(f"G03 {x_pos} Y0.{z2} {i_pos} J0. F{_f(feed, 2)}")


def _angle_from_horizontal(step: dict[str, Any]) -> float:
    """Return surface angle from the face (horizontal) for TNC / blend math.

    Chart Z° on SAE J1926 / ISO 6149 is from the *vertical* axis. Store that on
    the step as angle + angle_ref='from_vertical'. Convert here for formulas that
    expect θ from the face.
    """
    ang = float(step.get("angle", 0.0))
    if ang <= 0.0 or ang >= 89.95:
        return ang
    ref = str(step.get("angle_ref", "") or "").lower()
    # Default for truncated ORB / BSPP / cartridge leads: from vertical
    if ref in ("", "from_vertical", "vertical", "axis"):
        # Also treat unnamed Z-leads / SAE profiles as from vertical
        return max(0.0, 90.0 - ang)
    if ref in ("from_horizontal", "horizontal", "face"):
        return ang
    return max(0.0, 90.0 - ang)


def _tnc_shifts(radius: float, angle_from_face_deg: float) -> tuple[float, float]:
    """Tool-nose radius compensation for angled shoulders/chamfers.

    Z_shift = R * (1 - cos(θ))
    X_shift = R * (1 - sin(θ))
    where θ is the surface angle from horizontal (face).
    """
    if radius <= 0:
        return 0.0, 0.0
    theta = math.radians(max(0.0, min(90.0, angle_from_face_deg)))
    z_shift = radius * (1.0 - math.cos(theta))
    x_shift = radius * (1.0 - math.sin(theta))
    return z_shift, x_shift


def _safe_path_radius(
    target_dia: float,
    tool_dia: float,
    *,
    stock: float = 0.0,
    x_shift: float = 0.0,
    min_wall_clear: float = 0.002,
) -> tuple[float, bool]:
    """Interpolate radius so tool OD + stock stays inside the wall.

    Returns (path_r, ok). ok is False if the tool cannot fit without collision.
    """
    # Finished wall radius minus half tool, stock on walls, and TNC X shift
    path_r = (target_dia - tool_dia) / 2.0 - stock - x_shift - min_wall_clear
    if path_r <= 0.0:
        return 0.001, False
    return path_r, True


def geometry_warnings(
    cavity: dict[str, Any],
    endmill: dict[str, Any],
) -> list[str]:
    """Pre-flight checks for editable profiles vs tool size / corner radius."""
    warns: list[str] = []
    tool_dia = float(endmill.get("dia", 0.5))
    radius = float(endmill.get("radius", 0.0))
    profile = str(cavity.get("profile", "") or "").lower()
    # Truncated ORB only (SAE / ISO 6149) — not BSPP flats or deep cartridge steps
    is_truncated_orb = profile in ("sae_j1926", "iso_6149", "truncated_orb")
    chart_l1 = float(cavity.get("l1", 0.0) or 0.0)
    if chart_l1 <= 0.0 and isinstance(cavity.get("chart"), dict):
        chart_l1 = float(cavity["chart"].get("L1", 0.0) or 0.0)
    prev_dia: Optional[float] = None
    prev_depth = 0.0
    for step in cavity.get("steps", []):
        if step.get("is_spotface"):
            continue
        dia = float(step.get("dia", 0))
        depth = float(step.get("depth", 0))
        angle = float(step.get("angle", 0))
        ang_face = _angle_from_horizontal(step)
        name = step.get("name", "step")
        if dia <= tool_dia + 0.004:
            warns.append(
                f"{name}: feature Ø {dia:.4f}\" is too small for tool Ø {tool_dia:.4f}\" "
                f"— helix will skip or risk wall scrape."
            )
        z_shift, x_shift = _tnc_shifts(radius, ang_face if ang_face < 90 else 45.0)
        path_r, ok = _safe_path_radius(dia, tool_dia, stock=STOCK_ALLOWANCE, x_shift=x_shift)
        if not ok:
            warns.append(
                f"{name}: corner-radius / stock leave no safe interpolating radius "
                f"(need larger bore or smaller tool / radius)."
            )
        if prev_dia is not None and dia > prev_dia + 0.001:
            warns.append(
                f"{name}: Ø increases with depth ({prev_dia:.4f} -> {dia:.4f}) — "
                f"unusual for a stepped cavity; check print dims."
            )
        if depth + 1e-6 < prev_depth:
            warns.append(
                f"{name}: absolute Z {depth:.4f}\" is shallower than previous step "
                f"{prev_depth:.4f}\" — check from-spotface depths."
            )
        # Truncated ORB only: short angled zone — ignore deep cartridge / BSPP steps
        ff = float(step.get("from_face", 0.0) or 0.0)
        if is_truncated_orb and abs(angle - 45.0) < 1.0:
            l1_ref = chart_l1 if chart_l1 > 1e-4 else 0.098
            if ff > max(0.220, l1_ref * 2.5):
                warns.append(
                    f"{name}: from-spotface {ff:.3f}\" is far deeper than chart L1 "
                    f"≈ {l1_ref:.3f}\". Reset to defaults — looks like an old "
                    f"cylindrical O-ring gland, not truncated ORB."
                )
        # Lead Z for angled wall (chart angle from vertical → dz = dr / tan φ)
        if prev_dia is not None and 0.0 < angle < 90.0 and dia < prev_dia:
            rad_drop = (prev_dia - dia) / 2.0
            ref = str(step.get("angle_ref", "from_vertical") or "from_vertical").lower()
            if ref in ("from_horizontal", "horizontal", "face"):
                z_need = rad_drop * math.tan(math.radians(angle))
            else:
                z_need = rad_drop / math.tan(math.radians(angle))
            z_avail = depth - prev_depth
            # Cartridge leads are capped short — don't warn when max_lead is set
            if step.get("max_lead") is None and z_avail + 1e-4 < z_need * 0.5:
                warns.append(
                    f"{name}: {angle:.0f}° wall between Ø{prev_dia:.4f} and Ø{dia:.4f} "
                    f"wants ~{z_need:.4f}\" Z; available {z_avail:.4f}\" — may gouge or "
                    f"not form the full cone."
                )
        prev_dia = dia
        prev_depth = depth
    return warns


def _segment_depths(total_depth: float, flute_length: float) -> list[float]:
    """Return cumulative Z depths for segmented helix roughing."""
    if flute_length <= 0:
        return [total_depth]
    step = max(flute_length * FLUTE_SEGMENT_RATIO, 0.050)
    depths: list[float] = []
    z = 0.0
    while z < total_depth - 1e-6:
        z = min(z + step, total_depth)
        depths.append(round(z, 4))
    if not depths or depths[-1] < total_depth - 1e-6:
        depths.append(round(total_depth, 4))
    return depths


def _tool_number(tool: dict[str, Any], fallback: int = 1) -> int:
    tid = str(tool.get("id", ""))
    digits = "".join(ch for ch in tid if ch.isdigit())[:2]
    return int(digits) if digits else fallback


def _tooling_list_block(
    spot: dict[str, Any],
    pilot: dict[str, Any],
    endmill: dict[str, Any],
    thread_method: str,
    thread_tool: dict[str, Any],
) -> list[str]:
    """Fanuc-style parenthetical tooling list from the selected library tools."""

    def line_tool(role: str, tool: dict[str, Any], n: int) -> list[str]:
        tid = str(tool.get("id", f"T{n:02d}"))
        name = str(tool.get("name", ""))
        dia = float(tool.get("dia", tool.get("cutter_dia", 0.0)))
        rad = float(tool.get("radius", 0.0))
        reach = float(tool.get("reach", 0.0))
        flute = float(tool.get("flute", 0.0))
        rows = [
            f"(T{n:02d}  {role:<7}  {tid}  {name})",
            f"(      D{_f(dia)}  R{_f(rad)}  REACH {_f(reach, 3)}  FLUTE {_f(flute, 3)}  H{n:02d})",
        ]
        if tool.get("type") == "Tap" or role == "TAP":
            tpi = float(tool.get("tpi", 0) or 0)
            rows.append(f"(      PITCH/TPI {_f(tpi, 1)}  F={_f(1.0 / tpi if tpi else 0, 6)} IPR)")
        if tool.get("type") == "Threadmill" or role == "THRMILL":
            cd = float(tool.get("cutter_dia", dia))
            tmin = tool.get("tpi_min", "")
            tmax = tool.get("tpi_max", "")
            rows.append(f"(      CUTTER D{_f(cd)}  TPI RANGE {tmin}-{tmax})")
        return rows

    thr_role = "TAP" if thread_method == "Rigid Tap" else "THRMILL"
    lines = [
        "(==================== TOOLING LIST ====================)",
        "(FROM TOOL LIBRARY - TOOLS SELECTED FOR THIS PORT)",
    ]
    if str(spot.get("name", "")).lower() != "(skipped)":
        lines += line_tool("SPOT", spot, _tool_number(spot, 1))
    if str(pilot.get("name", "")).lower() != "(skipped)":
        lines += line_tool("PILOT", pilot, _tool_number(pilot, 2))
    lines += line_tool("EM", endmill, _tool_number(endmill, 4))
    lines += line_tool(thr_role, thread_tool, _tool_number(thread_tool, 6 if thr_role == "TAP" else 8))
    lines += [
        f"(WEAR OFFSET {WEAR_OFFSET_VAR} = EM DIA TRIM +/-0.002)",
    ]
    if thr_role == "THRMILL":
        lines.append(
            f"(WEAR OFFSET {TM_WEAR_OFFSET_VAR} = THREADMILL CUTTER DIA TRIM +/-0.002)"
        )
    lines += [
        "(======================================================)",
        "",
    ]
    return lines


def _header(
    standard: str,
    size: str,
    cavity: dict[str, Any],
    spot: dict[str, Any],
    pilot: dict[str, Any],
    endmill: dict[str, Any],
    thread_method: str,
    thread_tool: dict[str, Any],
) -> list[str]:
    lines = [
        "%",
        f"O8001 ({standard} {size} PORT/CAVITY)",
        f"(GENERATED {datetime.now().strftime('%Y-%m-%d %H:%M')})",
        f"(THREAD {cavity.get('thread', '')}  TOTAL DEPTH {_f(cavity['port_depth'])})",
        f"(SPOTFACE D{_f(float(cavity.get('spotface_dia', 0)))} "
        f"Z{_f(float(cavity.get('spotface_depth', 0)))})",
        "(UNITS INCH  ABS XY  FANUC)",
        "",
    ]
    lines += _tooling_list_block(spot, pilot, endmill, thread_method, thread_tool)
    lines += [
        "G90 G17 G20 G40 G80 G94",
        "G49 G69",
        f"{WEAR_OFFSET_VAR}=0.000",
    ]
    if thread_method == "Threadmill":
        lines.append(f"{TM_WEAR_OFFSET_VAR}=0.000")
    lines.append("")
    return lines


def _tool_change(tool: dict[str, Any], spindle: float, comment: str) -> list[str]:
    tid = tool.get("id", "T00")
    # Extract numeric tool number if present (T01_SPOT -> 1)
    num = "".join(ch for ch in tid if ch.isdigit())[:2] or "1"
    return [
        f"(--- {comment} ---)",
        f"T{int(num):02d} M06 ({tid} {tool.get('name', '')})",
        f"G00 G90 G54 X0. Y0.",
        f"G43 H{int(num):02d} Z{_f(RAPID_Z)}",
        f"S{int(spindle)} M03",
        "M08",
        "",
    ]


def _spot_cycle(tool: dict[str, Any], depth: float, feed: float) -> list[str]:
    z = -abs(min(depth, float(tool.get("flute", depth)) * 0.8, 0.150))
    return [
        f"(SPOT DRILL G82  DEPTH {_f(abs(z))})",
        f"G00 X0. Y0. Z{_f(SAFE_Z)}",
        f"G82 Z{_f(z)} R{_f(SAFE_Z)} P200 F{_f(feed, 2)}",
        "G80",
        "G00 Z" + _f(RAPID_Z),
        "M09",
        "M05",
        "",
    ]


def _pilot_cycle(tool: dict[str, Any], cavity_depth: float, feed: float) -> list[str]:
    z = -(abs(cavity_depth) - BOTTOM_CLEARANCE)
    peck = min(float(tool.get("flute", 0.5)) * 0.5, 0.250)
    peck = max(peck, 0.050)
    return [
        f"(PILOT PECK G83  TO {_f(abs(z))} = DEPTH-{_f(BOTTOM_CLEARANCE)} CLEAR)",
        f"G00 X0. Y0. Z{_f(SAFE_Z)}",
        f"G83 Z{_f(z)} R{_f(SAFE_Z)} Q{_f(peck)} F{_f(feed, 2)}",
        "G80",
        "G00 Z" + _f(RAPID_Z),
        "M09",
        "M05",
        "",
    ]


def _helix_to_diameter(
    lines: list[str],
    target_dia: float,
    tool_dia: float,
    z_start: float,
    z_end: float,
    feed: float,
    wear_comp: bool,
    rough_stock: float,
    label: str,
    *,
    pitch: float = HELIX_PITCH,
    wall_clear: bool = True,
) -> bool:
    """Helical interpolate from z_start to z_end at *pitch* Z per revolution.

    One rev = two 180° G03 semis. Returns False if the tool cannot fit.
    """
    path_r, ok = _safe_path_radius(target_dia, tool_dia, stock=rough_stock)
    if not ok:
        lines.append(f"(SKIP HELIX {label} — TOOL TOO LARGE FOR DIA {_f(target_dia)})")
        return False
    pitch = max(float(pitch), 0.005)
    if wear_comp:
        # Apply Fanuc wear var as diameter trim: R_adj = R + #501/2
        lines.append(
            f"(PATH R {_f(path_r)} + {WEAR_OFFSET_VAR}/2  "
            f"PITCH {_f(pitch)}/REV  [{label}])"
        )
        lines.append(f"#900=[{_f(path_r)}+[{WEAR_OFFSET_VAR}/2]]")
        lines.append("#910=-[#900]")
        r_pos = "#900"
        r_neg = "#910"
    else:
        lines.append(f"(PATH R {_f(path_r)}  PITCH {_f(pitch)}/REV  [{label}])")
        r_pos = _f(path_r)
        r_neg = _f(-path_r)

    z_travel = abs(z_end - z_start)
    revs = max(int(math.ceil(z_travel / pitch)), 1)
    dz = (z_end - z_start) / revs

    # Lead-in to helix start
    lines.append(f"G00 X0. Y0. Z{_f(SAFE_Z)}")
    lines.append(f"G01 Z{_f(z_start)} F{_f(feed, 2)}")
    if wear_comp:
        lines.append(f"G01 X[{r_pos}] Y0. F{_f(feed, 2)}")
    else:
        lines.append(f"G01 X{r_pos} Y0. F{_f(feed, 2)}")

    z = z_start
    for _i in range(revs):
        z_next = z + dz
        # Helix: one rev = two 180° semis with Z climb on each half
        _g03_two_semis(
            lines,
            r_pos,
            r_neg,
            feed,
            z_mid=z + dz / 2,
            z_end=z_next,
            use_brackets=wear_comp,
        )
        z = z_next

    if wall_clear:
        # Clear walls wider than shank before next plunge (flute-clearance protection)
        clear_r = path_r + 0.010
        lines.append("(WALL CLEAR BEFORE NEXT SEGMENT — TWO SEMI-ARCS)")
        if wear_comp:
            lines.append(f"#901=[{_f(clear_r)}+[{WEAR_OFFSET_VAR}/2]]")
            lines.append("#911=-[#901]")
            _g03_two_semis(lines, "#901", "#911", feed, use_brackets=True)
        else:
            _g03_two_semis(
                lines,
                _f(clear_r),
                _f(-clear_r),
                feed,
                use_brackets=False,
            )
    lines.append("G00 X0. Y0.")
    return True


def _is_cylinder_step(step: dict[str, Any]) -> bool:
    """True for vertical walls (SF / lands / minor) — not Z° or 45° form leads."""
    ang = abs(float(step.get("angle", 0.0) or 0.0))
    return ang < 2.0 or ang > 88.0


def _finish_step(
    lines: list[str],
    step: dict[str, Any],
    tool: dict[str, Any],
    feed: float,
    pitch: float,
    spring_pass: bool = True,
) -> None:
    """Finish a cylindrical Ø as one continuous helix at *pitch* Z/rev.

    Unlike roughing, this does **not** break into ~80% flute segments — the
    cutter stays engaged from near-face to full depth so size is set once with
    no leave/return recut. Still uses the same G03 semi-arc helix at pitch.
    Caller must run steps top→down so upper clearances already exist.
    Form features (Z° / 45°) are skipped — surfaced later.
    """
    if not _is_cylinder_step(step):
        lines.append(
            f"(SKIP FINISH HELIX {step.get('name', '')} — "
            f"ANGLE {_f(float(step.get('angle', 0)), 1)}° FORMED BY SURFACE PASS)"
        )
        return

    tool_dia = float(tool.get("dia", 0.5))
    target_dia = float(step["dia"])
    depth = float(step["depth"])
    z_end = -depth
    path_r, ok = _safe_path_radius(
        target_dia, tool_dia, stock=0.0, min_wall_clear=0.001
    )
    if not ok:
        lines.append(f"(SKIP FINISH {step.get('name', '')} — NO SAFE PATH RADIUS)")
        return

    lines.append(
        f"(FINISH CONTINUOUS HELIX {step.get('name', '')}  DIA {_f(target_dia)}  "
        f"Z {_f(depth)}  PITCH {_f(pitch)}/REV — NO FLUTE SEGMENTS)"
    )
    _helix_to_diameter(
        lines,
        target_dia=target_dia,
        tool_dia=tool_dia,
        z_start=-0.020,
        z_end=z_end,
        feed=feed,
        wear_comp=True,
        rough_stock=0.0,
        label=f"FINISH {step.get('name', '')}",
        pitch=pitch,
        wall_clear=False,
    )
    if spring_pass:
        lines.append(f"#900=[{_f(path_r)}+[{WEAR_OFFSET_VAR}/2]]")
        lines.append("#910=-[#900]")
        lines.append(f"G01 Z{_f(z_end)} F{_f(feed * 0.6, 2)}")
        lines.append(f"G01 X[#900] Y0. F{_f(feed, 2)}")
        lines.append("(SPRING PASS — TWO 180° SEMI-ARCS)")
        _g03_two_semis(lines, "#900", "#910", feed * 0.7, use_brackets=True)
        lines.append("G00 X0. Y0.")
    lines.append(f"G00 Z{_f(SAFE_Z)}")


def _ordered_bore_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Largest/shallowest first → smaller/deeper (clearance already open below)."""
    return sorted(
        steps,
        key=lambda s: (float(s.get("depth", 0.0)), -float(s.get("dia", 0.0))),
    )


def _segmented_helix_rough(
    tool: dict[str, Any],
    steps: list[dict[str, Any]],
    rough_feed: float,
    pitch: float,
) -> list[str]:
    lines = [
        "(BORE — SEGMENTED HELIX ROUGHING)",
        f"(STOCK LEFT ON WALLS {_f(STOCK_ALLOWANCE)})",
        f"(HELIX PITCH {_f(pitch)} Z PER REVOLUTION)",
        f"(MAX SEGMENT = {_f(FLUTE_SEGMENT_RATIO * 100, 0)}% OF FLUTE LENGTH)",
        "(ORDER: TOP / LARGER Ø FIRST, THEN DOWN — FLUTE CLEARANCE)",
        "",
    ]
    tool_dia = float(tool.get("dia", 0.5))
    flute = float(tool.get("flute", 0.5))

    for step in _ordered_bore_steps(steps):
        dia = float(step["dia"])
        depth = float(step["depth"])
        name = step.get("name", "STEP")
        if dia <= tool_dia + 0.002:
            lines.append(f"(SKIP {name} — DIA {_f(dia)} <= TOOL {_f(tool_dia)})")
            continue

        segment_zs = _segment_depths(depth, flute)
        lines.append(f"(ROUGH {name}  TARGET DIA {_f(dia)}  DEPTH {_f(depth)})")
        lines.append(f"(SEGMENTS: {', '.join(_f(z) for z in segment_zs)})")

        prev_z = 0.0
        for seg_z in segment_zs:
            lines.append(f"(SEGMENT Z {_f(prev_z)} -> {_f(seg_z)})")
            _helix_to_diameter(
                lines,
                target_dia=dia,
                tool_dia=tool_dia,
                z_start=-prev_z if prev_z > 0 else -0.020,
                z_end=-seg_z,
                feed=rough_feed,
                wear_comp=True,
                rough_stock=STOCK_ALLOWANCE,
                label=f"{name} Z-{_f(seg_z)}",
                pitch=pitch,
                wall_clear=True,
            )
            prev_z = seg_z
        lines.append("")

    lines.append(f"G00 Z{_f(RAPID_Z)}")
    return lines


def _finish_all(
    tool: dict[str, Any],
    steps: list[dict[str, Any]],
    finish_feed: float,
    pitch: float,
    cavity: dict[str, Any] | None = None,
) -> list[str]:
    lines = [
        "(FINISH BORE — CONTINUOUS HELIX @ PITCH, TOP TO BOTTOM)",
        f"({WEAR_OFFSET_VAR} MAPS TOOL DIA TRIM FOR +/-0.002 TOLERANCE)",
        f"(HELIX PITCH {_f(pitch)} Z PER REVOLUTION — SAME AS ROUGH)",
        "(No flute segments: stays engaged to depth; each Ø sized once — no recut)",
        "(Upper clearances first so shank is free on deeper Øs)",
        "",
    ]
    tool_dia = float(tool.get("dia", 0.5))
    cav = cavity or {"steps": steps}
    for step in _ordered_bore_steps(steps):
        if float(step["dia"]) <= tool_dia + 0.002:
            continue
        name = str(step.get("name", "")).lower()
        is_sf = bool(step.get("is_spotface")) or "spotface" in name
        # Spotface floor gets EM-bottom spiral later; wall still helix-finished
        spring = (not is_sf) and any(
            k in name for k in ("seal", "nose", "step 1", "o-ring")
        )
        _finish_step(lines, step, tool, finish_feed, pitch=pitch, spring_pass=spring)
        lines.append("")

    lines += _spotface_spiral_face(tool, cav, finish_feed)
    lines += _profile_surface_finish(tool, cav, finish_feed)

    lines.append(f"G00 Z{_f(RAPID_Z)}")
    lines.append("M09")
    lines.append("M05")
    lines.append("")
    return lines


def _spotface_depth_planes(depth: float) -> list[float]:
    """Positive Z depths in slices of SPOTFACE_MAX_DOC (0.030\")."""
    d = abs(float(depth))
    if d < 1e-6:
        return []
    n = max(int(math.ceil(d / SPOTFACE_MAX_DOC)), 1)
    return [d * (i / n) for i in range(1, n + 1)]


def _spiral_path_radii(final_path_r: float, stepover: float) -> list[float]:
    """Tool-center radii for outward face spiral ending at final_path_r."""
    if final_path_r <= 1e-6:
        return []
    stepover = max(float(stepover), 0.010)
    radii: list[float] = []
    r = min(stepover, final_path_r)
    while r < final_path_r - 1e-6:
        radii.append(r)
        r = min(r + stepover, final_path_r)
    if not radii or abs(radii[-1] - final_path_r) > 1e-6:
        radii.append(final_path_r)
    return radii


def _spotface_spiral_face(
    tool: dict[str, Any],
    cavity: dict[str, Any],
    feed: float,
) -> list[str]:
    """Face the spotface flat with the EM bottom — spiral out, final clean rev.

    Not wall-surfacing: Z DOC capped at 0.030\", radial stepover = 90% of EM Ø.
    """
    steps = list(cavity.get("steps") or [])
    sf = next((s for s in steps if s.get("is_spotface")), None)
    sf_dia = float(
        (sf or {}).get("dia", cavity.get("spotface_dia", 0.0)) or 0.0
    )
    sf_depth = float(
        (sf or {}).get("depth", cavity.get("spotface_depth", 0.0)) or 0.0
    )
    if sf_dia < 1e-4 or sf_depth < 1e-4:
        return ["(SPOTFACE SPIRAL SKIPPED — NO SF DIA/DEPTH)", ""]

    tool_dia = float(tool.get("dia", 0.5))
    final_path_r, ok = _safe_path_radius(
        sf_dia, tool_dia, stock=0.0, min_wall_clear=0.001
    )
    if not ok:
        return [
            f"(SPOTFACE SPIRAL SKIPPED — TOOL Ø{_f(tool_dia)} >= SF Ø{_f(sf_dia)})",
            "",
        ]

    stepover = tool_dia * SPOTFACE_STEPOVER_RATIO
    radii = _spiral_path_radii(final_path_r, stepover)
    planes = _spotface_depth_planes(sf_depth)
    if not radii or not planes:
        return ["(SPOTFACE SPIRAL SKIPPED — NOTHING TO CUT)", ""]

    lines = [
        "(SPOTFACE FACE — EM BOTTOM SPIRAL OUT)",
        f"(SF Ø{_f(sf_dia)}  DEPTH {_f(sf_depth)}  "
        f"STEPOVER {_f(stepover)} = {SPOTFACE_STEPOVER_RATIO * 100:.0f}% EM Ø  "
        f"MAX DOC {_f(SPOTFACE_MAX_DOC)})",
        f"(RINGS {len(radii)}  Z PASSES {len(planes)}  WEAR {WEAR_OFFSET_VAR})",
        "(Final revolution at SF path R keeps floor OD round)",
        "",
    ]

    for z_abs in planes:
        z = -z_abs
        lines.append(f"(SF FACE Z {_f(z_abs)} )")
        lines.append(f"G00 X0. Y0. Z{_f(SAFE_Z)}")
        lines.append(f"G01 Z{_f(z)} F{_f(feed * 0.5, 2)}")
        # Center dwell-cut with bottom of EM, then spiral rings outward
        for pr in radii:
            lines.append(f"#900=[{_f(pr)}+[{WEAR_OFFSET_VAR}/2]]")
            lines.append("#910=-[#900]")
            lines.append(f"G01 X[#900] Y0. F{_f(feed, 2)}")
            _g03_two_semis(lines, "#900", "#910", feed, use_brackets=True)
        # Final clean revolution at finished path R (round spotface OD)
        lines.append("(SF FINAL REVOLUTION — TWO 180° SEMI-ARCS)")
        lines.append(f"#900=[{_f(final_path_r)}+[{WEAR_OFFSET_VAR}/2]]")
        lines.append("#910=-[#900]")
        lines.append(f"G01 X[#900] Y0. F{_f(feed * 0.8, 2)}")
        _g03_two_semis(lines, "#900", "#910", feed * 0.8, use_brackets=True)
        lines.append("G00 X0. Y0.")
        lines.append(f"G00 Z{_f(SAFE_Z)}")
        lines.append("")

    return lines


def _is_fillet_or_chamfer_segment(
    r0: float, z0: float, r1: float, z1: float
) -> bool:
    """Keep only form features: fillet arcs and angled chamfers (ΔR and ΔZ).

    Skips vertical hole walls and horizontal floors — those are helix-finished.
    """
    dr = abs(r1 - r0)
    dz = abs(z1 - z0)
    if dr < 1e-4:
        return False  # cylinder
    if dz < 1e-4:
        return False  # flat floor / seal land
    return True


def _feature_wall_runs(
    wall: list[tuple[float, float]],
    *,
    fine_step: float,
) -> list[list[tuple[float, float]]]:
    """Densified polylines for fillet + chamfer regions only (contiguous runs)."""
    runs: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []

    def flush() -> None:
        nonlocal current
        if len(current) >= 2:
            runs.append(current)
        current = []

    for i in range(1, len(wall)):
        r0, z0 = wall[i - 1]
        r1, z1 = wall[i]
        if r1 < 0.02 and r0 > 0.05:
            break
        if not _is_fillet_or_chamfer_segment(r0, z0, r1, z1):
            flush()
            continue
        dist = math.hypot(r1 - r0, z1 - z0)
        if dist < 1e-6:
            continue
        if not current:
            current = [(r0, z0)]
        n = max(int(math.ceil(dist / fine_step)), 1)
        for k in range(1, n + 1):
            t = k / n
            current.append((r0 + (r1 - r0) * t, z0 + (z1 - z0) * t))
    flush()
    return runs


def _densify_wall(
    wall: list[tuple[float, float]],
    *,
    fine_step: float = SURFACE_WALL_STEP,
    cylinder_step: float = 0.025,
) -> list[tuple[float, float]]:
    """Sample wall polyline (legacy helper — prefer _feature_wall_runs)."""
    if not wall:
        return []
    out: list[tuple[float, float]] = [wall[0]]
    for i in range(1, len(wall)):
        r0, z0 = out[-1]
        r1, z1 = wall[i]
        if r1 < 0.02 and r0 > 0.05:
            break
        dist = math.hypot(r1 - r0, z1 - z0)
        if dist < 1e-6:
            continue
        step = fine_step if abs(r1 - r0) > 1e-4 else cylinder_step
        n = max(int(math.ceil(dist / step)), 1)
        for k in range(1, n + 1):
            t = k / n
            out.append((r0 + (r1 - r0) * t, z0 + (z1 - z0) * t))
    return out


def _surface_feature_run(
    lines: list[str],
    stations: list[tuple[float, float]],
    tool_dia: float,
    feed: float,
    run_idx: int,
) -> None:
    """Helical circular surfacing along one fillet/chamfer run."""
    r0, z0 = stations[0]
    path0, ok0 = _safe_path_radius(r0 * 2.0, tool_dia, stock=0.0, min_wall_clear=0.001)
    if not ok0:
        lines.append(f"(SKIP FEATURE RUN {run_idx} — TOOL TOO LARGE)")
        return

    lines.append(f"(FEATURE RUN {run_idx} — {len(stations)} STATIONS)")
    lines.append(f"#900=[{_f(path0)}+[{WEAR_OFFSET_VAR}/2]]")
    lines.append("#910=-[#900]")
    lines.append(f"G00 X0. Y0. Z{_f(SAFE_Z)}")
    lines.append(f"G01 Z{_f(-z0)} F{_f(feed * 0.5, 2)}")
    lines.append(f"G01 X[#900] Y0. F{_f(feed, 2)}")
    lines.append("(LEAD — TWO 180° SEMI-ARCS)")
    _g03_two_semis(lines, "#900", "#910", feed, use_brackets=True)

    prev_r, prev_z, prev_path = r0, z0, path0
    for r, z in stations[1:]:
        if abs(z - prev_z) < 1e-6 and abs(r - prev_r) < 1e-6:
            continue
        path_r, ok = _safe_path_radius(r * 2.0, tool_dia, stock=0.0, min_wall_clear=0.001)
        if not ok:
            lines.append(f"(SKIP STATION R{_f(r)} Z-{_f(z)} — NO CLEARANCE)")
            prev_r, prev_z = r, z
            continue

        lines.append(f"#900=[{_f(path_r)}+[{WEAR_OFFSET_VAR}/2]]")
        lines.append("#910=-[#900]")
        if abs(path_r - prev_path) > 1e-5:
            lines.append(f"G01 X[#900] Y0. F{_f(feed, 2)}")

        if abs(z - prev_z) < 1e-6:
            _g03_two_semis(lines, "#900", "#910", feed, use_brackets=True)
        else:
            _g03_two_semis(
                lines,
                "#900",
                "#910",
                feed,
                z_mid=-(prev_z + z) / 2.0,
                z_end=-z,
                use_brackets=True,
            )
        prev_r, prev_z, prev_path = r, z, path_r

    lines.append("G00 X0. Y0.")
    lines.append(f"G00 Z{_f(SAFE_Z)}")


def _profile_surface_finish(
    tool: dict[str, Any],
    cavity: dict[str, Any],
    feed: float,
) -> list[str]:
    """Surface fillet radii and chamfers/Z° only — not full hole walls.

    Cylinders and flats are finished by helix; this pass forms edge R, Z° and 45°.
    """
    try:
        from profile_preview import _wall_polyline
    except ImportError:
        return ["(PROFILE SURFACE SKIPPED — profile_preview not available)", ""]

    tool_dia = float(tool.get("dia", 0.5))
    corner_r = float(tool.get("radius", 0.0))
    steps = list(cavity.get("steps") or [])
    if not steps:
        return []

    wall = _wall_polyline(steps, profile=str(cavity.get("profile") or ""))
    wall = [(r, z) for r, z in wall if r > tool_dia / 2.0 + 0.005]
    fine = SURFACE_WALL_STEP
    if corner_r > 0.0:
        fine = min(SURFACE_WALL_STEP, max(0.001, corner_r * 0.2))
    runs = _feature_wall_runs(wall, fine_step=fine)
    if not runs:
        return [
            "(PROFILE SURFACE — NO FILLET/CHAMFER FEATURES FOUND)",
            "",
        ]

    n_stations = sum(len(r) for r in runs)
    lines = [
        "(PROFILE SURFACE — FILLET + CHAMFER / Z° ONLY)",
        f"(TOOL Ø{_f(tool_dia)}  CORNER R{_f(corner_r)}  FINE {_f(fine)}  "
        f"RUNS {len(runs)}  STATIONS {n_stations}  WEAR {WEAR_OFFSET_VAR})",
        "(Skips cylinders and spotface floor — helix + SF spiral already did those)",
        "",
    ]
    for i, stations in enumerate(runs, start=1):
        _surface_feature_run(lines, stations, tool_dia, feed, i)
        lines.append("")
    return lines


def _rigid_tap(
    tap: dict[str, Any],
    cavity: dict[str, Any],
    spindle: float,
) -> list[str]:
    tpi = float(tap.get("tpi", cavity.get("tpi", 16)))
    pitch = 1.0 / tpi
    z = -float(cavity.get("full_thread_min", cavity["port_depth"] * 0.6))
    tid = tap.get("id", "T06")
    num = "".join(ch for ch in tid if ch.isdigit())[:2] or "6"
    return [
        "(RIGID TAP G84.2)",
        f"T{int(num):02d} M06 ({tid} {tap.get('name', '')})",
        "G00 G90 G54 X0. Y0.",
        f"G43 H{int(num):02d} Z{_f(RAPID_Z)}",
        f"S{int(spindle)} M03",
        "M08",
        "G95 (FEED PER REVOLUTION)",
        f"(PITCH = 1/{_f(tpi, 1)} = {_f(pitch, 6)} IPR)",
        f"G00 Z{_f(SAFE_Z)}",
        f"G84.2 Z{_f(z)} R{_f(SAFE_Z)} F{_f(pitch, 6)}",
        "G80",
        "G94 (FEED PER MINUTE)",
        f"G00 Z{_f(RAPID_Z)}",
        "M09",
        "M05",
        "",
    ]


def _threadmill(
    tm: dict[str, Any],
    cavity: dict[str, Any],
    spindle: float,
    feed: float,
) -> list[str]:
    cutter = float(tm.get("cutter_dia", tm.get("dia", 0.290)))
    major = float(cavity.get("major_dia", 0.750))
    tpi = float(cavity.get("tpi", 16))
    pitch = 1.0 / tpi
    thread_depth = float(cavity.get("full_thread_min", 0.5))
    # Nominal path R; live dia trim via #502 (same sign convention as EM #501)
    path_r = (major - cutter) / 2.0
    z_start = -(thread_depth + 0.5 * pitch)
    z_end = -0.050
    turns = max(int(math.ceil(abs(z_end - z_start) / pitch)), 1)

    tid = tm.get("id", "T08")
    num = "".join(ch for ch in tid if ch.isdigit())[:2] or "8"

    lines = [
        "(THREADMILL - HELICAL ENTRY + CLIMB SPIRAL)",
        f"(PATH R = (MAJOR-CUTTER)/2 + {TM_WEAR_OFFSET_VAR}/2)",
        f"T{int(num):02d} M06 ({tid} {tm.get('name', '')})",
        "G00 G90 G54 X0. Y0.",
        f"G43 H{int(num):02d} Z{_f(RAPID_Z)}",
        f"S{int(spindle)} M03",
        "M08",
        f"(CUTTER DIA {_f(cutter)}  MAJOR {_f(major)}  NOM PATH R {_f(path_r)}  PITCH {_f(pitch, 6)})",
        f"#920=[{_f(path_r)}+[{TM_WEAR_OFFSET_VAR}/2]]",
        "#921=-[#920]",
        f"G00 Z{_f(SAFE_Z)}",
        "G00 X0. Y0.",
        f"G01 Z{_f(z_start)} F{_f(feed, 2)}",
        "(HELICAL ENTRY — TWO 180° SEMI-ARCS)",
        f"G01 X[#920] Y0. F{_f(feed * 0.5, 2)}",
    ]
    z_entry = z_start + pitch * 0.25
    _g03_two_semis(
        lines,
        "#920",
        "#921",
        feed * 0.6,
        z_mid=z_start + pitch * 0.125,
        z_end=z_entry,
        use_brackets=True,
    )
    lines.append(f"(CLIMB SPIRAL UP - {turns} TURNS — TWO SEMIS PER TURN)")
    z = z_entry
    for _i in range(turns):
        z_next = min(z + pitch, z_end)
        _g03_two_semis(
            lines,
            "#920",
            "#921",
            feed,
            z_mid=(z + z_next) / 2,
            z_end=z_next,
            use_brackets=True,
        )
        z = z_next
        if z >= z_end - 1e-6:
            break
    lines.append("(CLEAN RETRACT — TWO 180° SEMI-ARCS)")
    _g03_two_semis(lines, "#920", "#921", feed * 0.8, use_brackets=True)
    lines += [
        "G01 X0. Y0. F" + _f(feed, 2),
        f"G00 Z{_f(RAPID_Z)}",
        "M09",
        "M05",
        "",
    ]
    return lines


def generate_gcode(
    standard: str,
    size: str,
    cavity: dict[str, Any],
    spot: dict[str, Any],
    pilot: dict[str, Any],
    endmill: dict[str, Any],
    thread_method: str,
    thread_tool: dict[str, Any],
    rough_feed: float,
    finish_feed: float,
    spindle: float,
    *,
    helix_pitch: float = HELIX_PITCH,
    already_drilled: bool = False,
) -> str:
    pitch = max(float(helix_pitch), 0.005)
    lines: list[str] = []
    lines += _header(
        standard,
        size,
        cavity,
        spot,
        pilot,
        endmill,
        thread_method,
        thread_tool,
    )
    lines.append(f"(HELIX PITCH {_f(pitch)} Z PER REVOLUTION)")
    lines.append(
        "(ORDER: SPOT → PILOT → BORE → FINISH BORE → SF FACE → "
        "FILLET/CHAMFER SURFACE → THREAD)"
    )
    if already_drilled:
        lines.append("(HOLE ALREADY DRILLED — SKIP SPOT / PILOT)")
    lines.append("")

    # Reach check annotation
    reach = float(endmill.get("reach", 0))
    depth = float(cavity.get("port_depth", 0))
    if reach < depth:
        lines.append(f"(*** WARNING: EM REACH {_f(reach)} < CAVITY DEPTH {_f(depth)} ***)")
        lines.append("")

    if not already_drilled:
        # 1) Spot
        lines += _tool_change(spot, spindle, "SPOT DRILL")
        spot_depth = min(0.120, float(cavity.get("spotface_depth", 0.062)) + 0.060)
        lines += _spot_cycle(spot, spot_depth, rough_feed)

        # 2) Pilot peck
        lines += _tool_change(pilot, spindle, "PILOT DRILL")
        lines += _pilot_cycle(pilot, depth, rough_feed)

    # 3–6) EM: bore → finish bore → spotface spiral → fillet/chamfer surface
    lines += _tool_change(endmill, spindle * 1.2 if spindle < 6000 else spindle, "END MILL")
    steps = cavity.get("steps", [])
    lines.append("(BORE — SEGMENTED HELIX ROUGH)")
    lines.append("")
    lines += _segmented_helix_rough(endmill, steps, rough_feed, pitch=pitch)
    lines += _finish_all(endmill, steps, finish_feed, pitch=pitch, cavity=cavity)

    # 7) Threading
    if thread_method == "Rigid Tap":
        lines += _rigid_tap(thread_tool, cavity, min(spindle, 400))
    else:
        lines += _threadmill(thread_tool, cavity, spindle * 1.5 if spindle < 4000 else spindle, finish_feed)

    lines += [
        "(END OF PROGRAM)",
        "G00 G28 G91 Z0.",
        "G90",
        "M30",
        "%",
    ]
    return "\n".join(lines)


def reach_warning(endmill: dict[str, Any] | None, cavity: dict[str, Any] | None) -> str | None:
    if not endmill or not cavity:
        return None
    reach = float(endmill.get("reach", 0))
    depth = float(cavity.get("port_depth", 0))
    if reach < depth:
        return (
            f"TOOL REACH WARNING: Selected end mill reach/stick-out "
            f"({reach:.3f}\") is shorter than cavity depth ({depth:.3f}\"). "
            f"Risk of holder collision / incomplete machining."
        )
    return None
