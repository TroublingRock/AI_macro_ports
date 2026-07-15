"""
AI Macro Ports — Mobile-friendly Streamlit port & cavity G-code generator.
"""

from __future__ import annotations

import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import streamlit as st

from gcode_generator import generate_gcode, geometry_warnings, reach_warning
from profile_preview import cavity_preview_svg
from port_standards import (
    BUILTIN_NAMES,
    SHOP_SPOTFACE_DEPTH,
    apply_resolved_depths,
    clear_cavity_override,
    create_standard_set,
    get_cavity,
    has_override,
    is_custom_standard,
    list_sizes,
    list_standard_names,
    load_custom_standards,
    save_cavity_override,
    save_cavity_to_standard,
)
from tool_store import (
    CATEGORIES,
    delete_tool,
    find_tool,
    load_tools,
    save_tools,
    tools_by_type,
    upsert_tool,
)

# ---------------------------------------------------------------------------
# Page / theme
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="AI Macro Ports",
    page_icon="A",
    layout="centered",
    initial_sidebar_state="collapsed",
)

MOBILE_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');

:root {
  --ink: #1a2332;
  --muted: #5a6a7a;
  --bg: #f0f3f7;
  --card: #ffffff;
  --line: #d4dde8;
  --accent: #0c6e6b;
  --accent-2: #c45c26;
  --warn: #b91c1c;
  --warn-bg: #fef2f2;
  --ok: #0f766e;
  --radius: 14px;
  --shadow: 0 4px 20px rgba(26, 35, 50, 0.08);
}

html, body, [class*="css"] {
  font-family: 'DM Sans', system-ui, sans-serif !important;
  color: var(--ink);
}

.stApp {
  background:
    radial-gradient(1200px 600px at 10% -10%, #d9ebea 0%, transparent 55%),
    radial-gradient(900px 500px at 100% 0%, #f5e6dc 0%, transparent 50%),
    linear-gradient(180deg, #eef2f6 0%, #f7f9fb 40%, #eef2f6 100%);
}

/* Hide Streamlit chrome for cleaner mobile */
#MainMenu, footer, header { visibility: hidden; height: 0; }
div[data-testid="stToolbar"] { display: none; }
.block-container {
  padding-top: 1rem !important;
  padding-bottom: 4rem !important;
  padding-left: 1rem !important;
  padding-right: 1rem !important;
  max-width: 520px !important;
}

.hero {
  text-align: left;
  margin: 0.25rem 0 1.25rem 0;
}
.hero .brand {
  font-size: 1.75rem;
  font-weight: 700;
  letter-spacing: -0.03em;
  color: var(--ink);
  line-height: 1.15;
}
.hero .brand span { color: var(--accent); }
.hero .tag {
  margin-top: 0.35rem;
  font-size: 0.95rem;
  color: var(--muted);
  line-height: 1.4;
}

.panel {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 0.9rem 1rem;
  box-shadow: var(--shadow);
  margin-bottom: 0.85rem;
}
.panel h3 {
  margin: 0 0 0.35rem 0;
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--muted);
  font-weight: 600;
}

.warn-banner {
  background: var(--warn-bg);
  border: 2px solid var(--warn);
  border-radius: var(--radius);
  padding: 0.9rem 1rem;
  color: var(--warn);
  font-weight: 700;
  font-size: 0.95rem;
  line-height: 1.35;
  margin: 0.5rem 0 1rem 0;
  box-shadow: 0 0 0 4px rgba(185, 28, 28, 0.12);
}

.meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin: 0.4rem 0 0.8rem 0;
}
.chip {
  background: #e8eef4;
  color: var(--ink);
  font-size: 0.75rem;
  font-weight: 600;
  padding: 0.28rem 0.6rem;
  border-radius: 999px;
  border: 1px solid var(--line);
}

.gcode-box textarea, .stCodeBlock, pre {
  font-family: 'JetBrains Mono', ui-monospace, monospace !important;
  font-size: 0.72rem !important;
}

/* Touch-friendly controls */
.stSelectbox, .stNumberInput, .stTextInput, .stTextArea {
  margin-bottom: 0.15rem;
}
div[data-baseweb="select"] > div,
.stTextInput input, .stNumberInput input, .stTextArea textarea {
  min-height: 44px !important;
  border-radius: 10px !important;
}
.stButton > button {
  width: 100%;
  min-height: 48px;
  border-radius: 12px !important;
  font-weight: 600 !important;
  font-size: 0.95rem !important;
  border: none !important;
}
.stButton > button[kind="primary"],
.stButton > button[data-testid="baseButton-primary"] {
  background: linear-gradient(135deg, #0c6e6b, #0a5856) !important;
  color: #fff !important;
}
.stDownloadButton > button {
  width: 100%;
  min-height: 48px;
  border-radius: 12px !important;
  font-weight: 600 !important;
  background: linear-gradient(135deg, #1a2332, #2c3b50) !important;
  color: #fff !important;
  border: none !important;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
  gap: 0.35rem;
  background: transparent;
  border-bottom: 1px solid var(--line);
  padding-bottom: 0.35rem;
}
.stTabs [data-baseweb="tab"] {
  min-height: 44px;
  border-radius: 10px;
  padding: 0.4rem 0.9rem;
  font-weight: 600;
  background: #e5ebf1;
  color: var(--muted);
}
.stTabs [aria-selected="true"] {
  background: var(--accent) !important;
  color: #fff !important;
}

div[data-testid="stExpander"] {
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--card);
}

@media (max-width: 480px) {
  .hero .brand { font-size: 1.55rem; }
  .block-container { padding-left: 0.75rem !important; padding-right: 0.75rem !important; }
}
</style>
"""

st.markdown(MOBILE_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tool_label(t: dict[str, Any]) -> str:
    return f"{t.get('id', '?')} — {t.get('name', '')}"


def _options(tools: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {_tool_label(t): t for t in tools}


def send_nc_email(to_addr: str, filename: str, gcode: str, subject: str) -> tuple[bool, str]:
    try:
        sender = st.secrets["EMAIL_SENDER"]
        password = st.secrets["EMAIL_PASSWORD"]
    except Exception:
        return False, "SMTP secrets missing. Add EMAIL_SENDER and EMAIL_PASSWORD to .streamlit/secrets.toml"

    smtp_server = st.secrets.get("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(st.secrets.get("SMTP_PORT", 587))

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = to_addr
    msg["Subject"] = subject
    body = (
        "Attached is the NC program generated by AI Macro Ports.\n\n"
        f"File: {filename}\n"
        "Generated on a mobile Streamlit session."
    )
    msg.attach(MIMEText(body, "plain"))
    attachment = MIMEApplication(gcode.encode("utf-8"), Name=filename)
    attachment["Content-Disposition"] = f'attachment; filename="{filename}"'
    msg.attach(attachment)

    try:
        with smtplib.SMTP(smtp_server, smtp_port, timeout=30) as server:
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, [to_addr], msg.as_string())
        return True, f"Sent to {to_addr}"
    except Exception as exc:  # noqa: BLE001 — surface SMTP errors to user
        return False, f"Email failed: {exc}"


def init_state() -> None:
    if "tools" not in st.session_state:
        st.session_state.tools = load_tools()
    if "gcode" not in st.session_state:
        st.session_state.gcode = ""
    if "nc_name" not in st.session_state:
        st.session_state.nc_name = "PORT.NC"


init_state()

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.markdown(
    """
<div class="hero">
  <div class="brand">AI Macro <span>Ports</span></div>
  <div class="tag">Mobile port & cavity G-code — spot, pilot, bore, finish, SF face, fillet/chamfer surface, tap / threadmill.</div>
</div>
""",
    unsafe_allow_html=True,
)

tab_lib, tab_gen = st.tabs(["Tool Library", "Port & Cavity"])

# ===========================================================================
# TAB 1 — Tool Library
# ===========================================================================

with tab_lib:
    st.markdown('<div class="panel"><h3>Library</h3></div>', unsafe_allow_html=True)

    category = st.selectbox("Category", CATEGORIES, key="lib_category")
    tools_in_cat = st.session_state.tools.get(category, [])
    labels = [_tool_label(t) for t in tools_in_cat]

    if labels:
        selected_label = st.selectbox("Select tool", labels, key="lib_select")
        selected = next(t for t in tools_in_cat if _tool_label(t) == selected_label)
    else:
        selected = None
        st.info("No tools in this category yet. Add one below.")

    st.markdown("---")
    st.caption("Edit or create — changes save to tools.json on this device/server.")

    with st.form("tool_form", clear_on_submit=False):
        default = selected or {}
        is_new = st.checkbox("Create new tool", value=selected is None)

        col_a, col_b = st.columns(2)
        with col_a:
            tool_id = st.text_input(
                "Tool ID",
                value="" if is_new else str(default.get("id", "")),
                placeholder="T09_EM_NEW",
            )
        with col_b:
            tool_name = st.text_input(
                "Name",
                value="" if is_new else str(default.get("name", "")),
                placeholder="Description",
            )

        if category == "Taps":
            t_type = "Tap"
            tpi = st.number_input("Pitch / TPI", min_value=1.0, value=float(default.get("tpi", 16)), step=1.0)
            dia = st.number_input("Major Dia (in)", min_value=0.01, value=float(default.get("dia", 0.75)), step=0.001, format="%.4f")
            reach = st.number_input("Reach (in)", min_value=0.01, value=float(default.get("reach", 2.0)), step=0.01, format="%.3f")
            flute = st.number_input("Flute (in)", min_value=0.01, value=float(default.get("flute", 1.0)), step=0.01, format="%.3f")
            radius = 0.0
            cutter_dia = None
            tpi_min = tpi_max = None
        elif category == "Threadmills":
            t_type = "Threadmill"
            cutter_dia = st.number_input(
                "Cutter Dia (in)",
                min_value=0.01,
                value=float(default.get("cutter_dia", default.get("dia", 0.290))),
                step=0.001,
                format="%.4f",
            )
            c1, c2 = st.columns(2)
            with c1:
                tpi_min = st.number_input("Pitch/TPI min", min_value=1.0, value=float(default.get("tpi_min", 12)), step=1.0)
            with c2:
                tpi_max = st.number_input("Pitch/TPI max", min_value=1.0, value=float(default.get("tpi_max", 16)), step=1.0)
            reach = st.number_input("Reach (in)", min_value=0.01, value=float(default.get("reach", 1.5)), step=0.01, format="%.3f")
            flute = st.number_input("Flute (in)", min_value=0.01, value=float(default.get("flute", 0.75)), step=0.01, format="%.3f")
            dia = cutter_dia
            radius = 0.0
            tpi = None
        else:
            type_opts = ["Spot Drill", "Pilot Drill", "End Mill"]
            cur_type = str(default.get("type", "End Mill"))
            t_type = st.selectbox(
                "Type",
                type_opts,
                index=type_opts.index(cur_type) if cur_type in type_opts else 2,
            )
            d1, d2 = st.columns(2)
            with d1:
                dia = st.number_input("Dia (in)", min_value=0.01, value=float(default.get("dia", 0.5)), step=0.001, format="%.4f")
                radius = st.number_input("Corner Radius (in)", min_value=0.0, value=float(default.get("radius", 0.0)), step=0.001, format="%.4f")
            with d2:
                reach = st.number_input("Reach (in)", min_value=0.01, value=float(default.get("reach", 1.5)), step=0.01, format="%.3f")
                flute = st.number_input("Flute (in)", min_value=0.01, value=float(default.get("flute", 0.75)), step=0.01, format="%.3f")
            cutter_dia = None
            tpi = tpi_min = tpi_max = None

        save_clicked = st.form_submit_button("Save to tools.json", type="primary", use_container_width=True)

        if save_clicked:
            if not tool_id.strip() or not tool_name.strip():
                st.error("Tool ID and Name are required.")
            else:
                payload: dict[str, Any] = {
                    "id": tool_id.strip(),
                    "name": tool_name.strip(),
                    "type": t_type,
                    "dia": float(dia),
                    "radius": float(radius),
                    "reach": float(reach),
                    "flute": float(flute),
                }
                if category == "Taps":
                    payload["tpi"] = float(tpi)  # type: ignore[arg-type]
                if category == "Threadmills":
                    payload["cutter_dia"] = float(cutter_dia)  # type: ignore[arg-type]
                    payload["tpi_min"] = float(tpi_min)  # type: ignore[arg-type]
                    payload["tpi_max"] = float(tpi_max)  # type: ignore[arg-type]
                st.session_state.tools = upsert_tool(st.session_state.tools, category, payload)
                save_tools(st.session_state.tools)
                st.success(f"Saved {payload['id']} to tools.json")
                st.rerun()

    if selected and not st.session_state.get("_skip_delete"):
        if st.button("Delete selected tool", use_container_width=True):
            st.session_state.tools = delete_tool(st.session_state.tools, selected["id"])
            save_tools(st.session_state.tools)
            st.success(f"Deleted {selected['id']}")
            st.rerun()

    with st.expander("Preview tools.json"):
        for cat in CATEGORIES:
            st.markdown(f"**{cat}**")
            for t in st.session_state.tools.get(cat, []):
                extra = ""
                if t.get("type") == "Tap":
                    extra = f" · {t.get('tpi')} TPI"
                elif t.get("type") == "Threadmill":
                    extra = f" · ⌀{t.get('cutter_dia')} · {t.get('tpi_min')}-{t.get('tpi_max')} TPI"
                else:
                    extra = (
                        f" · ⌀{t.get('dia')} · R{t.get('radius')} · "
                        f"Reach {t.get('reach')} · Flute {t.get('flute')}"
                    )
                st.caption(f"`{t.get('id')}` {t.get('name')}{extra}")

# ===========================================================================
# TAB 2 — Port & Cavity Generator
# ===========================================================================

with tab_gen:
    st.markdown('<div class="panel"><h3>Port standard</h3></div>', unsafe_allow_html=True)

    std_names = list_standard_names()
    standard = st.selectbox("Port Standard", std_names, key="std")
    sizes = list_sizes(standard)

    with st.expander("Custom standard sets", expanded=is_custom_standard(standard) and not sizes):
        new_set = st.text_input("New standard set name", placeholder="My Shop Ports", key="new_set_name")
        if st.button("Create standard set", use_container_width=True):
            ok, msg = create_standard_set(new_set)
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)
        custom_names = list(load_custom_standards().keys())
        if custom_names:
            st.caption("Custom sets: " + ", ".join(custom_names))
        st.caption(
            "Edit any port below, then use Save into standard set to add it to a custom list."
        )

    if not sizes:
        st.info(
            f"'{standard}' has no ports yet. Select a built-in port, edit it, then "
            "Save into this set."
        )
        # Fall back to first built-in so the form stays usable
        fallback = next(iter(BUILTIN_NAMES))
        sizes = list_sizes(fallback)
        size = st.selectbox(f"Edit from ({fallback})", sizes, key="size_fallback")
        source_standard = fallback
    else:
        size = st.selectbox("Size", sizes, key="size")
        source_standard = standard

    geom_key = f"geom::v7::{source_standard}::{size}"
    if st.session_state.get("geom_key") != geom_key or geom_key not in st.session_state:
        st.session_state[geom_key] = get_cavity(source_standard, size, shop_defaults=True)
        st.session_state["geom_key"] = geom_key
        # Drop stale widget / old-version keys — never delete the active cavity blob
        stale_prefixes = (
            f"geom::{source_standard}::{size}",
            f"geom::v2::{source_standard}::{size}",
            f"geom::v3::{source_standard}::{size}",
            f"geom::v4::{source_standard}::{size}",
            f"geom::v5::{source_standard}::{size}",
            f"geom::v6::{source_standard}::{size}",
            f"{geom_key}_",  # number inputs keyed off current geom_key
        )
        for k in list(st.session_state.keys()):
            if not isinstance(k, str) or k == geom_key:
                continue
            if any(k.startswith(p) for p in stale_prefixes):
                st.session_state.pop(k, None)

    if geom_key not in st.session_state:
        st.session_state[geom_key] = get_cavity(source_standard, size, shop_defaults=True)
        st.session_state["geom_key"] = geom_key

    cavity = st.session_state[geom_key]

    chips = [
        f"Thread {cavity.get('thread', '')}",
        f"Depth {cavity.get('port_depth', 0):.3f}\"",
    ]
    if cavity.get("pitch_mm"):
        chips.append(f"Pitch {cavity['pitch_mm']} mm")
    if cavity.get("description"):
        chips.append(cavity["description"])
    if is_custom_standard(standard):
        chips.append("Custom set")
    chip_html = "".join(f'<span class="chip">{c}</span>' for c in chips)
    st.markdown(f'<div class="meta-row">{chip_html}</div>', unsafe_allow_html=True)

    # --- Editable profile (print = from spotface; mill uses absolute Z) ---
    st.markdown("#### Cavity profile (print dims from spotface)")
    chart_max = float(cavity.get("chart_spotface_max", cavity.get("spotface_depth", 0.03)))
    if cavity.get("using_saved_profile") or has_override(source_standard, size):
        st.caption(
            "Using saved shop override for this port. "
            "If you do not see **45 to minor**, hit Reset to defaults or Clear saved."
        )
    st.caption(
        "Print shape (SAE J1926): SF floor → R → Z° for chart L1 (long face) → short 45° → minor. "
        f"Change spotface depth and every abs Z moves with it. Shop SF default "
        f"{SHOP_SPOTFACE_DEPTH:.3f}\" (chart L3/E MAX {chart_max:.3f}\"). "
        "Cartridge mid-steps stay editable 45° defaults."
    )

    sf_steps = cavity.get("steps", [])
    sf_step = next((s for s in sf_steps if s.get("is_spotface")), sf_steps[0] if sf_steps else {})
    other_steps = [s for s in sf_steps if not s.get("is_spotface")]

    st.markdown("**Spotface + angled wall (tied together)**")
    s1, s2 = st.columns(2)
    with s1:
        sf_dia = st.number_input(
            "Spotface Ø (in)",
            min_value=0.010,
            value=float(sf_step.get("dia", cavity.get("spotface_dia", 0.5))),
            step=0.001,
            format="%.4f",
            key=f"{geom_key}_sf_dia",
        )
    with s2:
        sf_depth = st.number_input(
            "Spotface depth (in)",
            min_value=0.001,
            value=float(cavity.get("spotface_depth", SHOP_SPOTFACE_DEPTH)),
            step=0.001,
            format="%.4f",
            key=f"{geom_key}_sf_dep",
            help="Changing this shifts every step's absolute Z. Print 'from face' dims stay put.",
        )

    st.markdown("**Print features (depths & angles from spotface)**")
    st.caption(
        "Print shape: SF floor → R → Z° for chart L1 (longer face) → short 45° tip → minor. "
        "Fillet R is the floor→Z° edge break (SAE R0.1–0.2 mm / shop 0.010)."
    )
    edited_others: list[dict] = []
    for i, step in enumerate(other_steps):
        step_name = str(step.get("name", f"Step {i + 1}"))
        st.markdown(f"**{i + 1}. {step_name}**")
        show_fillet = (
            "seat" in step_name.lower()
            or "o-ring" in step_name.lower()
            or "z lead" in step_name.lower()
            or float(step.get("fillet_r", 0) or 0) > 1e-4
        )
        cols = st.columns(4 if show_fillet else 3)
        with cols[0]:
            dia = st.number_input(
                "Ø (in)",
                min_value=0.010,
                value=float(step.get("dia", 0.5)),
                step=0.001,
                format="%.4f",
                key=f"{geom_key}_dia_{i}",
            )
        with cols[1]:
            from_face = st.number_input(
                "From spotface (in)",
                min_value=0.001,
                value=float(step.get("from_face", step.get("depth", 0.1))),
                step=0.001,
                format="%.4f",
                key=f"{geom_key}_ff_{i}",
                help="As called out on the print, from the spot/seal face.",
            )
        with cols[2]:
            angle = st.number_input(
                "Angle (°)",
                min_value=0.0,
                max_value=90.0,
                value=float(step.get("angle", 0.0)),
                step=1.0,
                format="%.1f",
                key=f"{geom_key}_ang_{i}",
            )
        if show_fillet:
            with cols[3]:
                fillet_r = st.number_input(
                    "SF fillet R (in)",
                    min_value=0.0,
                    value=float(step.get("fillet_r", 0.010) or 0.010),
                    step=0.001,
                    format="%.4f",
                    key=f"{geom_key}_fil_{i}",
                    help="Convex edge R from spotface floor into Z° (SAE R0.1–0.2 mm ≈ 0.010\").",
                )
        else:
            fillet_r = float(step.get("fillet_r", 0.0) or 0.0)

        abs_z = float(sf_depth) + float(from_face)
        st.caption(
            f"Mill absolute Z: {abs_z:.4f}\"  (= SF {sf_depth:.4f} + {from_face:.4f})"
            + (f"  |  fillet R{float(fillet_r):.4f}" if show_fillet else "")
        )

        row = dict(step)
        row["name"] = step_name
        row["dia"] = float(dia)
        row["from_face"] = float(from_face)
        row["angle"] = float(angle)
        row["fillet_r"] = float(fillet_r)
        row["is_spotface"] = False
        edited_others.append(row)

    cavity["spotface_dia"] = float(sf_dia)
    cavity["spotface_depth"] = float(sf_depth)
    cavity["depth_mode"] = "from_seal_face"
    cavity["steps"] = [
        {
            "name": sf_step.get("name", "Spotface"),
            "dia": float(sf_dia),
            "from_face": 0.0,
            "angle": 90.0,
            "is_spotface": True,
        },
        *edited_others,
    ]
    apply_resolved_depths(cavity)
    st.session_state[geom_key] = cavity

    st.markdown("#### Profile preview")
    st.caption("Cross-section from face (Z down). Updates when you change a value (Enter or click away).")
    step_names = " → ".join(
        f"{s.get('name')} ({float(s.get('angle', 0)):.0f}°"
        + (f", R{float(s.get('fillet_r', 0)):.3f}" if float(s.get('fillet_r', 0) or 0) > 0 else "")
        + ")"
        for s in cavity.get("steps", [])
    )
    st.caption(step_names)
    st.markdown(cavity_preview_svg(cavity), unsafe_allow_html=True)

    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("Save override", use_container_width=True):
            save_cavity_override(source_standard, size, cavity)
            st.success(f"Saved override for {size}")
            st.rerun()
    with b2:
        if st.button("Reset to defaults", use_container_width=True):
            for k in list(st.session_state.keys()):
                if isinstance(k, str) and k.startswith(geom_key):
                    st.session_state.pop(k, None)
            st.session_state[geom_key] = get_cavity(
                source_standard, size, shop_defaults=True, use_override=False
            )
            st.rerun()
    with b3:
        if st.button("Clear saved / chart MAX SF", use_container_width=True):
            clear_cavity_override(source_standard, size)
            for k in list(st.session_state.keys()):
                if isinstance(k, str) and k.startswith(geom_key):
                    st.session_state.pop(k, None)
            st.session_state[geom_key] = get_cavity(
                source_standard, size, shop_defaults=False, use_override=False
            )
            st.rerun()

    st.markdown("**Save into a standard set**")
    custom_sets = list(load_custom_standards().keys())
    if not custom_sets:
        st.caption("Create a custom standard set above first.")
    else:
        sc1, sc2 = st.columns(2)
        with sc1:
            target_set = st.selectbox("Standard set", custom_sets, key="save_set")
        with sc2:
            save_as = st.text_input(
                "Size name in set",
                value=size,
                key=f"save_as_name::{standard}::{size}",
            )
        if st.button("Save edited port into set", type="primary", use_container_width=True):
            ok, msg = save_cavity_to_standard(target_set, save_as, cavity)
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    # Tool assignment
    drills = tools_by_type(st.session_state.tools, {"spot drill", "pilot drill", "end mill"})
    spots = tools_by_type(st.session_state.tools, {"spot drill"}) or drills
    pilots = tools_by_type(st.session_state.tools, {"pilot drill"}) or drills
    endmills = tools_by_type(st.session_state.tools, {"end mill"}) or drills
    taps = tools_by_type(st.session_state.tools, {"tap"})
    threadmills = tools_by_type(st.session_state.tools, {"threadmill"})

    spot_map = _options(spots)
    pilot_map = _options(pilots)
    em_map = _options(endmills)

    st.markdown("#### Tools")
    already_drilled = st.checkbox(
        "Skip spot & pilot (hole already drilled)",
        value=False,
        key="already_drilled",
        help="Default order is spot → pilot → bore → finish → SF face → surface → thread.",
    )
    spot: dict = {"id": "T01", "name": "(skipped)", "dia": 0.25, "type": "Spot Drill"}
    pilot: dict = {"id": "T02", "name": "(skipped)", "dia": 0.25, "type": "Pilot Drill"}
    if already_drilled:
        st.caption("Spot / pilot skipped — EM starts at bore.")
    else:
        if not spot_map or not pilot_map:
            st.error("Add spot and pilot drills in the Tool Library.")
        else:
            spot_key = st.selectbox("Spot Drill", list(spot_map.keys()), key="spot")
            pilot_key = st.selectbox("Pilot Drill", list(pilot_map.keys()), key="pilot")
            spot = spot_map[spot_key]
            pilot = pilot_map[pilot_key]
    if not em_map:
        st.error("Add an end mill in the Tool Library.")
        st.stop()
    em_key = st.selectbox("End Mill", list(em_map.keys()), key="em")
    endmill = em_map[em_key]

    warn = reach_warning(endmill, cavity)
    if warn:
        st.markdown(f'<div class="warn-banner">{warn}</div>', unsafe_allow_html=True)

    for gw in geometry_warnings(cavity, endmill):
        st.warning(gw)

    thread_method = st.selectbox("Threading Method", ["Rigid Tap", "Threadmill"], key="thr_method")

    if thread_method == "Rigid Tap":
        if not taps:
            st.error("No taps in the Tool Library. Add one in Tab 1.")
            thread_tool = None
        else:
            tap_map = _options(taps)
            thread_tool = tap_map[st.selectbox("Tap", list(tap_map.keys()), key="tap")]
    else:
        if not threadmills:
            st.error("No threadmills in the Tool Library. Add one in Tab 1.")
            thread_tool = None
        else:
            tm_map = _options(threadmills)
            thread_tool = tm_map[st.selectbox("Threadmill", list(tm_map.keys()), key="tm")]

    st.markdown("#### Feeds & speeds")
    f1, f2 = st.columns(2)
    with f1:
        rough_feed = st.number_input("Rough Feed (IPM)", min_value=0.1, value=12.0, step=0.5)
        finish_feed = st.number_input("Finish Feed (IPM)", min_value=0.1, value=8.0, step=0.5)
    with f2:
        spindle = st.number_input("Spindle RPM", min_value=50.0, value=2400.0, step=50.0)
        helix_pitch = st.number_input(
            "Helix pitch (Z / rev)",
            min_value=0.005,
            max_value=0.250,
            value=0.050,
            step=0.005,
            format="%.3f",
            help="Axial distance per full revolution for rough and finish diameter helixes.",
        )

    gen = st.button("Generate G-Code", type="primary", use_container_width=True)

    if gen:
        if not already_drilled and (
            str(spot.get("name", "")).lower() == "(skipped)"
            or str(pilot.get("name", "")).lower() == "(skipped)"
        ):
            st.error("Select spot and pilot drills, or check skip spot & pilot.")
        elif thread_tool is None:
            st.error("Select a threading tool before generating.")
        else:
            live = apply_resolved_depths(dict(st.session_state[geom_key]))
            st.session_state[geom_key] = live

            gcode = generate_gcode(
                standard=standard,
                size=size,
                cavity=live,
                spot=spot,
                pilot=pilot,
                endmill=endmill,
                thread_method=thread_method,
                thread_tool=thread_tool,
                rough_feed=float(rough_feed),
                finish_feed=float(finish_feed),
                spindle=float(spindle),
                helix_pitch=float(helix_pitch),
                already_drilled=bool(already_drilled),
            )
            safe_size = size.replace("/", "-").replace(" ", "")
            st.session_state.gcode = gcode
            st.session_state.nc_name = f"{safe_size}_PORT.NC"
            st.success("G-code ready — paths use the profile values above.")

    if st.session_state.gcode:
        st.markdown("#### Output")
        st.code(st.session_state.gcode, language="nc")

        st.download_button(
            label="Download .NC File",
            data=st.session_state.gcode.encode("utf-8"),
            file_name=st.session_state.nc_name,
            mime="text/plain",
            use_container_width=True,
        )

        with st.expander("Email to Work", expanded=False):
            email_to = st.text_input("Work email", placeholder="you@shop.com", key="email_to")
            if st.button("Send NC via Email", use_container_width=True):
                if not email_to or "@" not in email_to:
                    st.error("Enter a valid email address.")
                else:
                    ok, msg = send_nc_email(
                        email_to,
                        st.session_state.nc_name,
                        st.session_state.gcode,
                        subject=f"NC: {st.session_state.nc_name}",
                    )
                    if ok:
                        st.success(msg)
                    else:
                        st.error(msg)
