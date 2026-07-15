"""Cross-section preview for port / cavity standards.

Profiles
--------
sae_j1926 / ISO 6149-1 truncated ORB
  SF wall + flat floor → convex edge R → Z° (from vertical) → 45° → minor

bspp_flat (ISO 1179-1)
  SF wall + flat floor (seal face) → R/45° into thread → minor
  (no Z° undercut — seal is on the spotface flat)

cartridge_steps
  SF wall + floor → successive leads (from vertical) between step Øs
  OEM form-tool geometry varies — verify to print before cutting

Z0 is boss top. Print from_face depths are from the spotface floor.
"""

from __future__ import annotations

import math
from typing import Any


def _convex_edge_floor_to_cone(
    r_floor_od: float,
    z_floor: float,
    r_d5: float,
    angle_from_vertical_deg: float,
    fillet: float,
) -> list[tuple[float, float]]:
    """Flat spotface floor → convex edge R into Z° cone (from vertical).

    Matches SAE detail: R0.1–0.2 (shop ~0.010) rounds the ID lip of the
    spotface floor into the undercut — a convex edge break, not a CB floor fillet.
    """
    pts: list[tuple[float, float]] = [(r_floor_od, z_floor)]
    R = max(float(fillet), 0.0)
    phi = math.radians(max(min(angle_from_vertical_deg, 89.0), 0.05))
    # Z° from vertical: down/in unit T = (−sin φ, cos φ); metal outward ~ (+cos φ, sin φ)

    if R <= 1e-6 or r_floor_od <= r_d5:
        pts.append((r_d5, z_floor))
        return pts

    # Dual-tangent: center in the *metal* under the floor / outboard of the tip
    # so the arc removes the sharp lip (convex shoulder).
    # Sharp tip at (r_d5, z_floor). Offsets into metal:
    #   floor → z = z_floor + R
    #   cone  → shifted along metal normal
    # Intersection:
    s, c = math.sin(phi), math.cos(phi)
    # Cone sharp: r = r_d5 - (z - z_floor)*tan(φ) = r_d5 - (z - z_floor)*s/c
    # Metal-side parallel (offset +R along N≈(c, s) for small φ geometry):
    # Use center such that:
    #   north-west attach lands on floor inboard of OD, arc digs tip then hits Z°.
    # Exact for face∥horizontal and wall at φ from vertical (turn = 90°−φ):
    cx = r_d5 + R * c
    cy = z_floor + R
    # Face attach (above center): may sit outboard of r_d5 — floor from OD to attach
    r_attach = cx
    if r_attach > r_floor_od - 1e-6:
        # R too big for annulus — clamp attach under OD
        cx = r_floor_od - 1e-6
        r_attach = cx
        cy = z_floor + R

    if r_attach < r_floor_od - 1e-6:
        pts.append((r_attach, z_floor))

    # Start a = −π/2 (on floor). Sweep so tangent matches Z° heading T=(−s, c).
    # Heading turn from west (−1,0) to (−s,c) is (90°−φ).
    # a_end: velocity with da<0 matches T → a = −π + φ
    # Wait — with metal-outboard C, start is north: for C=(cx,cy) with cx>r_d5,
    # north attach (cx,z_floor) is outboard of tip. Sweep toward −r/down:
    # decreasing a: −π/2 → −π + φ
    a0 = -math.pi / 2.0
    a1 = -math.pi + phi
    # Heading turn only (90−φ): for φ=15°, sweep=75° — correct for floor→near-vertical.
    n = 12
    for i in range(1, n + 1):
        a = a0 + (a1 - a0) * (i / n)
        pts.append((cx + R * math.cos(a), cy + R * math.sin(a)))

    return pts


def _sae_z45_junction(
    r_d5: float,
    r_tap: float,
    z_sf: float,
    l1_z: float,
    z_deg: float,
) -> tuple[float, float, float]:
    """Return (z_j, r_j, z_end45) for Parker-style truncated ORB.

    Chart L1 is the Z° depth from the spotface floor (long nearly-vertical
    face). A short 45° (from vertical) then closes into the minor — matching
    the port sheet where Z° reads longer than the 45° tip.
    """
    phi = math.radians(max(min(z_deg, 80.0), 0.5))
    tan_z = math.tan(phi)
    l1_z = max(float(l1_z), 0.020)
    # Prefer Z° for full L1, then short 45° for remaining radial
    r_j = r_d5 - l1_z * tan_z
    min_rj = r_tap + 0.008
    if r_j < min_rj:
        # L1 too deep for this Ø stack (stale gland dims) — shorten Z°
        r_j = min_rj
        z_j = z_sf + (r_d5 - r_j) / tan_z
    else:
        z_j = z_sf + l1_z
    # 45° from vertical: axial = radial
    z_end45 = z_j + max(r_j - r_tap, 0.008)
    return z_j, r_j, z_end45


def _sae_wall_from_steps(steps: list[dict[str, Any]]) -> list[tuple[float, float]] | None:
    """Build SAE J1926 truncated ORB: SF floor → R → long Z° → short 45° → minor."""
    ordered = sorted(steps, key=lambda s: float(s.get("depth", 0.0)))
    sf = next((s for s in ordered if s.get("is_spotface")), None)
    if not sf:
        return None

    others = [s for s in ordered if not s.get("is_spotface")]
    if len(others) < 2:
        return None

    z_step = next(
        (s for s in others if float(s.get("fillet_r", 0) or 0) > 1e-4
         or "seat" in str(s.get("name", "")).lower()
         or "o-ring" in str(s.get("name", "")).lower()
         or "z lead" in str(s.get("name", "")).lower()
         or str(s.get("name", "")).lower().startswith("z")),
        others[0],
    )
    ang45 = next(
        (s for s in others if abs(float(s.get("angle", 0)) - 45.0) < 1.0),
        None,
    )
    minor = next(
        (s for s in reversed(others) if abs(float(s.get("angle", 0))) < 0.05
         or "minor" in str(s.get("name", "")).lower()
         or "thread" in str(s.get("name", "")).lower()),
        others[-1],
    )
    if ang45 is None:
        angled = [s for s in others if 0.5 < float(s.get("angle", 0)) < 89]
        ang45 = angled[1] if len(angled) > 1 else angled[0] if angled else minor

    r_sf = float(sf["dia"]) / 2.0
    z_sf = float(sf.get("depth", 0.0))
    r_d5 = float(z_step["dia"]) / 2.0
    z_deg = float(z_step.get("angle", 15.0))
    fillet = float(z_step.get("fillet_r", 0.010) or 0.010)
    # Chart L1 = end of Z° (prefer Z-step from_face; else derive from 45 step)
    if "from_face" in z_step and float(z_step.get("from_face") or 0) > 1e-4:
        l1_z = float(z_step["from_face"])
    elif "from_face" in ang45:
        # Legacy: 45 from_face stored chart L1 as if it ended the angle package
        l1_z = float(ang45["from_face"])
    else:
        l1_z = max(float(z_step.get("depth", z_sf)) - z_sf, 0.05)
    r_tap = float(ang45["dia"]) / 2.0
    if "from_face" in minor:
        z_tap = z_sf + float(minor["from_face"])
    else:
        z_tap = float(minor.get("depth", z_sf + l1_z + 0.2))

    tan_z = math.tan(math.radians(max(min(z_deg, 80.0), 0.5)))
    z_j, r_j, z_end45 = _sae_z45_junction(r_d5, r_tap, z_sf, l1_z, z_deg)
    # If 45 step lists a deeper from_face, honor it as end of 45° (won't shorten Z°)
    if "from_face" in ang45:
        z_end_print = z_sf + float(ang45["from_face"])
        if z_end_print > z_j + 0.005:
            z_end45 = max(z_end45, z_end_print)

    pts: list[tuple[float, float]] = []
    pts.append((r_sf, 0.0))
    pts.append((r_sf, z_sf))

    edge = _convex_edge_floor_to_cone(r_sf, z_sf, r_d5, z_deg, fillet)
    if pts and edge:
        if abs(edge[0][0] - pts[-1][0]) < 1e-6 and abs(edge[0][1] - pts[-1][1]) < 1e-6:
            edge = edge[1:]
    pts.extend(edge)

    def r_on_z(z: float) -> float:
        return r_d5 - (z - z_sf) * tan_z

    last_r, last_z = pts[-1]
    if last_z < z_j - 1e-5:
        z0 = max(last_z, z_sf)
        n_z = max(int(round((z_j - z0) / 0.008)), 2)
        for i in range(1, n_z + 1):
            z = z0 + (z_j - z0) * (i / n_z)
            pts.append((max(r_on_z(z), r_tap + 0.001), z))
    else:
        pts.append((r_j, z_j))

    pts.append((r_tap, z_end45))
    if z_tap > z_end45 + 1e-5:
        pts.append((r_tap, z_tap))
    pts.append((0.0, max(z_tap, z_end45)))
    return pts


def _cone_then_land(
    r_start: float,
    z_start: float,
    angle_deg: float,
    r_target: float,
    z_target: float,
    *,
    from_vertical: bool = False,
    max_lead: float | None = None,
) -> list[tuple[float, float]]:
    """Cone (or capped short lead) then cylindrical land to z_target."""
    pts: list[tuple[float, float]] = [(r_start, z_start)]
    if angle_deg <= 0.05 or abs(r_start - r_target) < 1e-6:
        pts.append((r_target, z_target))
        return pts

    theta = math.radians(angle_deg)
    dr = r_start - r_target
    if dr > 1e-6 and angle_deg < 89.5:
        if from_vertical:
            dz_cone = dr / math.tan(theta) if math.tan(theta) > 1e-9 else dr
        else:
            dz_cone = dr * math.tan(theta)
        if max_lead is not None and max_lead > 1e-4:
            dz_cone = min(dz_cone, float(max_lead))
        z_at_dia = z_start + dz_cone
        avail = z_target - z_start
        if avail + 1e-5 < dz_cone:
            # Not enough depth for full cone — taper what we can, land at target Ø
            pts.append((r_target, z_target))
        else:
            pts.append((r_target, z_at_dia))
            if z_target > z_at_dia + 1e-5:
                pts.append((r_target, z_target))
    else:
        pts.append((r_target, z_start))
        pts.append((r_target, z_target))
    return pts


def _bspp_wall_from_steps(steps: list[dict[str, Any]]) -> list[tuple[float, float]] | None:
    """ISO 1179-1 flat-face: SF wall + seal floor → short R/45° → tap blank."""
    ordered = sorted(steps, key=lambda s: float(s.get("depth", 0.0)))
    sf = next((s for s in ordered if s.get("is_spotface")), None)
    if not sf:
        return None
    others = [s for s in ordered if not s.get("is_spotface")]
    if not others:
        return None
    chamfer = next(
        (s for s in others if 20.0 < float(s.get("angle", 0)) < 70.0),
        others[0],
    )
    minor = others[-1]
    r_sf = float(sf["dia"]) / 2.0
    z_sf = float(sf.get("depth", 0.0))
    r_tap = float(chamfer["dia"]) / 2.0
    fillet = float(chamfer.get("fillet_r", 0.008) or 0.008)
    # Short tip only (capped) — seal is the flat SF floor, not a long funnel
    l1 = min(max(float(chamfer.get("from_face", 0.030)), 0.012), 0.060)
    z_end = z_sf + l1
    r_start = min(r_tap + l1, r_sf - 0.002)
    if "from_face" in minor:
        z_tap = z_sf + float(minor["from_face"])
    else:
        z_tap = float(minor.get("depth", z_end + 0.2))

    pts: list[tuple[float, float]] = [(r_sf, 0.0), (r_sf, z_sf)]
    edge = _convex_edge_floor_to_cone(r_sf, z_sf, r_start, 45.0, fillet)
    if pts and edge:
        if abs(edge[0][0] - pts[-1][0]) < 1e-6 and abs(edge[0][1] - pts[-1][1]) < 1e-6:
            edge = edge[1:]
    pts.extend(edge)
    last_r, last_z = pts[-1]
    if last_z < z_end - 1e-5:
        pts.append((r_tap, z_end))
    else:
        pts.append((r_tap, max(z_end, last_z)))
    if z_tap > z_end + 1e-5:
        pts.append((r_tap, z_tap))
    pts.append((0.0, max(z_tap, z_end)))
    return pts


def _cartridge_wall_from_steps(steps: list[dict[str, Any]]) -> list[tuple[float, float]]:
    """Stepped cartridge: SF + short leads (capped) + cylindrical lands."""
    ordered = sorted(steps, key=lambda s: float(s.get("depth", 0.0)))
    pts: list[tuple[float, float]] = []
    prev_r = float(ordered[0].get("dia", 0.5)) / 2.0
    prev_z = 0.0
    pts.append((prev_r, 0.0))

    for i, step in enumerate(ordered):
        z = float(step.get("depth", 0.0))
        r_next = float(step.get("dia", 0.0)) / 2.0
        angle = float(step.get("angle", 45.0))
        fillet = float(step.get("fillet_r", 0.0) or 0.0)
        is_sf = bool(step.get("is_spotface"))
        max_lead = step.get("max_lead")
        if max_lead is None:
            max_lead = 0.070 if i == 1 else 0.080
        else:
            max_lead = float(max_lead)

        if is_sf:
            if abs(r_next - prev_r) > 1e-6:
                pts.append((r_next, prev_z))
            pts.append((r_next, z))
            prev_r, prev_z = r_next, z
            continue

        if abs(r_next - prev_r) < 1e-6 or angle < 0.05:
            pts.append((r_next, z))
            prev_r, prev_z = r_next, z
            continue

        if angle >= 89.5:
            pts.append((r_next, prev_z))
            pts.append((r_next, z))
            prev_r, prev_z = r_next, z
            continue

        # Optional convex R only on first diameter drop off the SF floor
        if i == 1 and fillet > 1e-4 and abs(prev_z) > 1e-6:
            # Fillet into a short lead start radius (not full step Ø cone)
            edge = _convex_edge_floor_to_cone(prev_r, prev_z, r_next, angle, fillet)
            if pts and edge:
                if abs(edge[0][0] - pts[-1][0]) < 1e-6 and abs(edge[0][1] - pts[-1][1]) < 1e-6:
                    edge = edge[1:]
            pts.extend(edge)
            last_r, last_z = pts[-1]
            blend = _cone_then_land(
                last_r,
                last_z,
                angle,
                r_next,
                z,
                from_vertical=True,
                max_lead=max_lead,
            )
            if blend and abs(blend[0][0] - last_r) < 1e-6 and abs(blend[0][1] - last_z) < 1e-6:
                blend = blend[1:]
            pts.extend(blend)
        else:
            blend = _cone_then_land(
                prev_r,
                prev_z,
                angle,
                r_next,
                z,
                from_vertical=True,
                max_lead=max_lead,
            )
            if pts and blend:
                if abs(blend[0][0] - pts[-1][0]) < 1e-6 and abs(blend[0][1] - pts[-1][1]) < 1e-6:
                    blend = blend[1:]
            pts.extend(blend)
        prev_r, prev_z = r_next, z

    pts.append((0.0, prev_z))
    return pts


def _wall_polyline(
    steps: list[dict[str, Any]],
    *,
    profile: str | None = None,
) -> list[tuple[float, float]]:
    """Right-hand wall (radius, depth+) — mill absolute Z, boss top = 0."""
    if not steps:
        return [(0.0, 0.0)]

    prof = (profile or "").lower()
    if prof in ("sae_j1926", "iso_6149", "truncated_orb"):
        wall = _sae_wall_from_steps(steps)
        if wall:
            return wall
    if prof == "bspp_flat":
        wall = _bspp_wall_from_steps(steps)
        if wall:
            return wall
    if prof == "cartridge_steps":
        return _cartridge_wall_from_steps(steps)

    # Infer from step names if profile missing
    names = " ".join(str(s.get("name", "")).lower() for s in steps)
    if "z lead" in names or ("o-ring" in names and "45" in names):
        wall = _sae_wall_from_steps(steps)
        if wall:
            return wall
    if "45 into minor" in names:
        wall = _bspp_wall_from_steps(steps)
        if wall:
            return wall
    if any("step" in str(s.get("name", "")).lower() for s in steps):
        return _cartridge_wall_from_steps(steps)

    wall = _sae_wall_from_steps(steps)
    if wall:
        return wall
    return _cartridge_wall_from_steps(steps)


def cavity_preview_svg(cavity: dict[str, Any], width: int = 420, height: int = 340) -> str:
    """SVG cross-section — equal scale so chart angles read true."""
    steps = list(cavity.get("steps") or [])
    if not steps:
        return "<svg></svg>"

    profile = str(cavity.get("profile") or "")
    right = _wall_polyline(steps, profile=profile)
    left = [(-r, z) for r, z in reversed(right)]
    poly = left + right

    max_r = max(abs(r) for r, _ in poly) or 0.5
    max_z = max(z for _, z in poly) or 0.5
    max_r *= 1.03
    pad = 28
    footer = 18
    plot_w = width - 2 * pad
    plot_h = height - 2 * pad - footer

    span_r = 2.0 * max_r
    span_z = max_z
    scale = min(plot_w / span_r, plot_h / span_z)
    used_w = span_r * scale
    used_h = span_z * scale
    ox = pad + (plot_w - used_w) * 0.5
    oy = pad + 8 + (plot_h - used_h) * 0.5

    def tx(r: float) -> float:
        return ox + (r + max_r) * scale

    def ty(z: float) -> float:
        return oy + z * scale

    points = " ".join(f"{tx(r):.1f},{ty(z):.1f}" for r, z in poly)

    sf = next((s for s in steps if s.get("is_spotface")), None)
    z_sf = float(sf.get("depth", 0.0)) if sf else 0.0

    labels: list[str] = []
    for step in sorted(steps, key=lambda s: float(s.get("depth", 0))):
        dia = float(step["dia"])
        z_abs = float(step["depth"])
        name = str(step.get("name", ""))[:16]
        ang = float(step.get("angle", 0))
        fr = float(step.get("fillet_r", 0) or 0)
        from_face = float(step.get("from_face", max(z_abs - z_sf, 0.0)))
        if step.get("is_spotface"):
            z_show = z_sf
            depth_note = f"SF Z-{z_sf:.3f}"
            extra = ""
        else:
            extra = f"  {ang:.0f}deg" if 0 < ang < 90 else ""
            if fr > 0:
                extra += f"  R{fr:.3f}"
            z_show = z_abs
            # Mill abs Z + print from-spotface (so deep seat typos stand out)
            depth_note = f"Z-{z_abs:.3f} ({from_face:.3f} face)"
        labels.append(
            f'<text x="{tx(dia / 2) + 4:.1f}" y="{ty(z_show) - 3:.1f}" '
            f'font-size="10" fill="#5a6a7a">{name}</text>'
            f'<text x="{tx(dia / 2) + 4:.1f}" y="{ty(z_show) + 10:.1f}" '
            f'font-size="9" fill="#0c6e6b">Ø{dia:.3f}  {depth_note}{extra}</text>'
        )

    foot = {
        "sae_j1926": "Truncated ORB: SF floor + convex R + Z° + 45°",
        "bspp_flat": "BSPP flat-face: SF floor + R/45° into thread",
        "cartridge_steps": "Cartridge: SF floor + stepped leads (verify OEM print)",
    }.get(profile, "SF floor + chart leads | equal scale")

    axis = (
        f'<line x1="{tx(0):.1f}" y1="{oy:.1f}" x2="{tx(0):.1f}" y2="{ty(max_z):.1f}" '
        f'stroke="#c5d0dc" stroke-dasharray="4 3"/>'
        f'<line x1="{tx(-max_r):.1f}" y1="{ty(0):.1f}" x2="{tx(max_r):.1f}" y2="{ty(0):.1f}" '
        f'stroke="#c5d0dc"/>'
        f'<text x="{pad:.1f}" y="{height - 6:.1f}" font-size="10" fill="#5a6a7a">'
        f'{foot}</text>'
    )

    return f"""
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"
     viewBox="0 0 {width} {height}" role="img" aria-label="Port cross-section">
  <rect width="100%" height="100%" fill="#f7fafc" rx="12"/>
  <polygon points="{points}" fill="#d9ebea" stroke="#0c6e6b" stroke-width="2"
           fill-opacity="0.55"/>
  {axis}
  {''.join(labels)}
</svg>
""".strip()
