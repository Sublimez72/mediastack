"""SABnzbd (optional, COMPOSE_PROFILES=usenet): login, folders, categories, provider."""
import json
import os
import re

from ..common import CONFIG, Api, ApiError, Ctx, Log, md5, wait_for, write_private

BASE = "http://sabnzbd:8080"
INI = CONFIG / "sabnzbd" / "sabnzbd.ini"
SERVER = "provider"                                 # the server entry stack-init manages
SERVER_STATE = CONFIG / "stack" / "usenet-server.md5"  # detects a changed USENET_PASSWORD


def enabled() -> bool:
    return "usenet" in os.environ.get("COMPOSE_PROFILES", "").replace(" ", "").split(",")


def api_key() -> str | None:
    if not INI.is_file():
        return None
    m = re.search(r"^api_key\s*=\s*(\S+)", INI.read_text(), re.M)
    return m.group(1) if m else None


class Sab:
    def __init__(self, key: str):
        self.api = Api(BASE)
        self.key = key

    def call(self, mode, **params):
        r = self.api.get("/api", params={"mode": mode, "apikey": self.key, "output": "json", **params})
        if not isinstance(r, dict):   # e.g. "Access denied - Hostname verification failed"
            raise ApiError(f"sabnzbd {mode}: {str(r)[:200]} (is 'sabnzbd' in host_whitelist in sabnzbd.ini?)")
        if r.get("status") is False:
            raise ApiError(f"sabnzbd {mode} {params.get('keyword', '')}: {r.get('error')}")
        return r

    def config(self, section):
        return (self.call("get_config", section=section).get("config") or {}).get(section) or []


def _norm(v) -> str:
    """SABnzbd returns bools as 0/1 and lists as lists; compare everything as text."""
    if isinstance(v, bool):
        return str(int(v))
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    return "" if v is None else str(v)


def configure(ctx: Ctx):
    if not enabled():
        return
    Log.section("sabnzbd")
    if not wait_for(f"{BASE}/api?mode=version", timeout=180):
        Log.warn("sabnzbd did not come up, skipping (`docker compose logs sabnzbd`)")
        return
    key = api_key()
    if not key:
        Log.warn("sabnzbd: no api_key in config/sabnzbd/sabnzbd.ini yet, skipping")
        return
    ctx.keys["sabnzbd"] = key
    sab = Sab(key)
    cfg = ctx.cfg.get("sabnzbd") or {}
    _misc(ctx, sab, cfg.get("misc") or {})
    _categories(ctx, sab, cfg.get("categories") or {})
    _server(ctx, sab, cfg.get("server") or {})


def _misc(ctx, sab, wanted):
    cur = sab.config("misc")
    want = {k: _norm(v) for k, v in wanted.items()} | {"username": ctx.user}
    drift = {k: v for k, v in want.items() if _norm(cur.get(k)) != v}
    if ctx.password_changed or not cur.get("password"):
        drift["password"] = ctx.password
    if not drift:
        return
    shown = ", ".join(f"{k}={'***' if k == 'password' else v}" for k, v in drift.items())

    def write():
        for k, v in drift.items():
            sab.call("set_config", section="misc", keyword=k, value=v)
    ctx.apply(f"sabnzbd: settings {shown}", write)


def _categories(ctx, sab, wanted):
    have = {c["name"]: c for c in sab.config("categories")}
    for name, path in wanted.items():
        cur = have.get(name)
        if cur and cur.get("dir", "").rstrip("/") == path.rstrip("/"):
            continue
        ctx.apply(f"sabnzbd: category {name} -> {path}",
                  lambda n=name, p=path: sab.call("set_config", section="categories", keyword=n, dir=p))


def _server(ctx, sab, extra):
    host = os.environ.get("USENET_HOST", "").strip()
    if not host:
        Log.info("no USENET_HOST in .env: add your Usenet provider in SABnzbd (Config > Servers)")
        return
    password = os.environ.get("USENET_PASSWORD", "")
    want = {
        "host": host,
        "displayname": host,
        "port": os.environ.get("USENET_PORT") or 563,
        "username": os.environ.get("USENET_USERNAME", ""),
        "connections": os.environ.get("USENET_CONNECTIONS") or 8,
        "ssl": 1,
        "enable": 1,
        **extra,
    }
    want = {k: _norm(v) for k, v in want.items()}
    fingerprint = md5(json.dumps({**want, "password": password}, sort_keys=True))
    cur = next((s for s in sab.config("servers") if s["name"] == SERVER), None)
    stored = SERVER_STATE.read_text().strip() if SERVER_STATE.is_file() else None
    if cur and stored == fingerprint and all(_norm(cur.get(k)) == v for k, v in want.items()):
        return

    def write():
        sab.call("set_config", section="servers", keyword=SERVER, password=password, **want)
        write_private(SERVER_STATE, fingerprint + "\n")
    ctx.apply(f"sabnzbd: Usenet server {host}:{want['port']} ({'update' if cur else 'new'})", write)
