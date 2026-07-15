"""Local JSON tool library persistence (optional GitHub sync on Cloud)."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from github_persist import load_json, save_json

TOOLS_PATH = Path(__file__).resolve().parent / "tools.json"

CATEGORIES = ("Drills/End Mills", "Taps", "Threadmills")

DEFAULT_TOOLS: dict[str, list[dict[str, Any]]] = {
    "Drills/End Mills": [
        {
            "id": "T01_SPOT",
            "name": "1/2 Spot Drill",
            "dia": 0.500,
            "radius": 0.0,
            "reach": 1.5,
            "flute": 0.5,
            "type": "Spot Drill",
        },
        {
            "id": "T02_PILOT_08",
            "name": "15/32 Pilot Drill (C08)",
            "dia": 0.468,
            "radius": 0.0,
            "reach": 2.0,
            "flute": 1.25,
            "type": "Pilot Drill",
        },
        {
            "id": "T03_PILOT_16",
            "name": "63/64 Pilot Drill (C16)",
            "dia": 0.984,
            "radius": 0.0,
            "reach": 5.0,
            "flute": 4.25,
            "type": "Pilot Drill",
        },
        {
            "id": "T04_EM_STD",
            "name": "1/2 Carbide End Mill",
            "dia": 0.500,
            "radius": 0.030,
            "reach": 1.5,
            "flute": 0.75,
            "type": "End Mill",
        },
        {
            "id": "T05_EM_DEEP",
            "name": "3/8 Deep Port End Mill",
            "dia": 0.375,
            "radius": 0.010,
            "reach": 4.5,
            "flute": 0.5,
            "type": "End Mill",
        },
    ],
    "Taps": [
        {
            "id": "T06_TAP_16",
            "name": "3/4-16 Tap",
            "type": "Tap",
            "tpi": 16,
            "dia": 0.750,
            "reach": 2.0,
            "flute": 1.0,
            "radius": 0.0,
        },
        {
            "id": "T07_TAP_12",
            "name": "1-5/16-12 Tap",
            "type": "Tap",
            "tpi": 12,
            "dia": 1.3125,
            "reach": 2.5,
            "flute": 1.25,
            "radius": 0.0,
        },
    ],
    "Threadmills": [
        {
            "id": "T08_TM_GEN",
            "name": "Double End Threadmill",
            "type": "Threadmill",
            "cutter_dia": 0.290,
            "tpi_min": 12,
            "tpi_max": 16,
            "dia": 0.290,
            "reach": 1.5,
            "flute": 0.75,
            "radius": 0.0,
        },
    ],
}


def _ensure_structure(data: Any) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(data, dict):
        return deepcopy(DEFAULT_TOOLS)
    out: dict[str, list[dict[str, Any]]] = {}
    for cat in CATEGORIES:
        tools = data.get(cat, [])
        if not isinstance(tools, list):
            tools = []
        out[cat] = tools
    return out


def load_tools() -> dict[str, list[dict[str, Any]]]:
    raw = load_json(TOOLS_PATH, None)
    if raw is None:
        save_tools(DEFAULT_TOOLS)
        return deepcopy(DEFAULT_TOOLS)
    return _ensure_structure(raw)


def save_tools(tools: dict[str, list[dict[str, Any]]]) -> tuple[bool, str]:
    cleaned = _ensure_structure(tools)
    return save_json(TOOLS_PATH, cleaned, message="Update tools.json from AI Macro Ports")


def flatten_tools(tools: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    flat: list[dict[str, Any]] = []
    for cat, items in tools.items():
        for t in items:
            row = dict(t)
            row["category"] = cat
            flat.append(row)
    return flat


def find_tool(tools: dict[str, list[dict[str, Any]]], tool_id: str) -> dict[str, Any] | None:
    for items in tools.values():
        for t in items:
            if t.get("id") == tool_id:
                return t
    return None


def tools_by_type(
    tools: dict[str, list[dict[str, Any]]],
    types: set[str] | list[str],
) -> list[dict[str, Any]]:
    wanted = {t.lower() for t in types}
    return [t for t in flatten_tools(tools) if str(t.get("type", "")).lower() in wanted]


def upsert_tool(
    tools: dict[str, list[dict[str, Any]]],
    category: str,
    tool: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    data = deepcopy(tools)
    if category not in data:
        data[category] = []
    tid = tool.get("id")
    for cat in list(data.keys()):
        data[cat] = [t for t in data[cat] if t.get("id") != tid]
    data[category].append(tool)
    return data


def delete_tool(
    tools: dict[str, list[dict[str, Any]]],
    tool_id: str,
) -> dict[str, list[dict[str, Any]]]:
    data = deepcopy(tools)
    for cat in data:
        data[cat] = [t for t in data[cat] if t.get("id") != tool_id]
    return data
