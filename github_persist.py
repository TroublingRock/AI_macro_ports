"""Persist shop JSON to GitHub so Streamlit Cloud saves survive reboots.

Configure in .streamlit/secrets.toml (or Streamlit Cloud Secrets):

[github]
token = "ghp_..."   # classic PAT with repo scope, or fine-grained Contents: Read/Write
repo = "TroublingRock/AI_macro_ports"
branch = "main"

Optional env fallbacks: GITHUB_TOKEN, GITHUB_REPO, GITHUB_BRANCH.
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent

# In-process cache so load_* isn't spamming the API every widget rerun
_mem: dict[str, tuple[float, Any]] = {}
_MEM_TTL_S = 45.0
_last_error: Optional[str] = None
_last_ok: Optional[str] = None


def last_persist_error() -> Optional[str]:
    return _last_error


def last_persist_ok() -> Optional[str]:
    return _last_ok


def persist_enabled() -> bool:
    cfg = _config()
    return bool(cfg and cfg.get("token") and cfg.get("repo"))


def persist_status() -> str:
    if not persist_enabled():
        return "Local disk only (add GitHub secrets for Cloud persistence)."
    cfg = _config() or {}
    return f"GitHub sync on → {cfg.get('repo')} @ {cfg.get('branch')}"


def _config() -> Optional[dict[str, str]]:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPO", "").strip()
    branch = os.environ.get("GITHUB_BRANCH", "main").strip() or "main"

    try:
        import streamlit as st

        secrets = st.secrets
        gh = {}
        try:
            raw = secrets.get("github", {})
            if raw is not None:
                gh = dict(raw)
        except Exception:
            gh = {}
        token = str(gh.get("token") or secrets.get("GITHUB_TOKEN", token) or "").strip()
        repo = str(gh.get("repo") or secrets.get("GITHUB_REPO", repo) or "").strip()
        branch = str(gh.get("branch") or secrets.get("GITHUB_BRANCH", branch) or "main").strip()
    except Exception:
        pass

    if not token or not repo:
        return None
    if "/" not in repo:
        return None
    return {"token": token, "repo": repo, "branch": branch}


def _api_request(
    method: str,
    url: str,
    token: str,
    body: Optional[dict[str, Any]] = None,
) -> tuple[int, Any]:
    data = None
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "AI-macro-ports",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(err_body) if err_body else {}
        except json.JSONDecodeError:
            payload = {"message": err_body}
        return e.code, payload


def _rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def _cache_get(key: str) -> Optional[Any]:
    hit = _mem.get(key)
    if not hit:
        return None
    ts, data = hit
    if time.time() - ts > _MEM_TTL_S:
        return None
    return data


def _cache_set(key: str, data: Any) -> None:
    _mem[key] = (time.time(), data)


def _cache_clear(key: Optional[str] = None) -> None:
    if key is None:
        _mem.clear()
    else:
        _mem.pop(key, None)


def _read_local(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if data is not None else default
    except (json.JSONDecodeError, OSError):
        return default


def _write_local(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def _fetch_github(path: Path) -> tuple[Optional[Any], Optional[str]]:
    """Return (parsed_json, sha) or (None, None) if missing / unavailable."""
    global _last_error
    from urllib.parse import quote

    cfg = _config()
    if not cfg:
        return None, None
    rel = _rel(path)
    url = (
        f"https://api.github.com/repos/{cfg['repo']}/contents/{quote(rel)}"
        f"?ref={quote(cfg['branch'])}"
    )
    code, payload = _api_request("GET", url, cfg["token"])
    if code == 404:
        return None, None
    if code >= 400:
        _last_error = f"GitHub read {rel}: {payload.get('message', code)}"
        return None, None
    content_b64 = payload.get("content")
    sha = payload.get("sha")
    if not content_b64:
        return None, None
    try:
        text = base64.b64decode(content_b64.replace("\n", "")).decode("utf-8")
        return json.loads(text), sha
    except (ValueError, json.JSONDecodeError) as e:
        _last_error = f"GitHub parse {rel}: {e}"
        return None, None


def _push_github(path: Path, data: Any, message: str) -> bool:
    global _last_error, _last_ok
    cfg = _config()
    if not cfg:
        return False
    from urllib.parse import quote

    rel = _rel(path)
    url = f"https://api.github.com/repos/{cfg['repo']}/contents/{quote(rel)}"
    # Need current sha for updates
    _, sha = _fetch_github(path)
    text = json.dumps(data, indent=2) + "\n"
    body: dict[str, Any] = {
        "message": message,
        "content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
        "branch": cfg["branch"],
    }
    if sha:
        body["sha"] = sha
    code, payload = _api_request("PUT", url, cfg["token"], body)
    if code >= 400:
        _last_error = f"GitHub write {rel}: {payload.get('message', code)}"
        _last_ok = None
        return False
    _last_error = None
    _last_ok = f"Synced {rel} → {cfg['repo']}"
    return True


def load_json(path: Path, default: Any) -> Any:
    """Load JSON: GitHub (when configured) with local fallback + cache."""
    key = str(path.resolve())
    cached = _cache_get(key)
    if cached is not None:
        return cached

    if persist_enabled():
        remote, _ = _fetch_github(path)
        if remote is not None:
            try:
                _write_local(path, remote)
            except OSError:
                pass
            _cache_set(key, remote)
            return remote

    local = _read_local(path, default)
    _cache_set(key, local)
    return local


def save_json(path: Path, data: Any, message: Optional[str] = None) -> tuple[bool, str]:
    """Write local JSON and, when configured, push to GitHub."""
    key = str(path.resolve())
    try:
        _write_local(path, data)
    except OSError as e:
        return False, f"Could not write {path.name}: {e}"

    _cache_set(key, data)
    if not persist_enabled():
        return True, f"Saved {path.name} (local only)."

    rel = _rel(path)
    msg = message or f"Update {rel} from AI Macro Ports"
    if _push_github(path, data, msg):
        return True, f"Saved {path.name} and synced to GitHub."
    err = last_persist_error() or "GitHub sync failed."
    return True, f"Saved {path.name} locally, but GitHub sync failed: {err}"
