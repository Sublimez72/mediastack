"""qBittorrent (behind gluetun): login, preferences, categories."""
import json

from ..common import Api, Ctx, Log, wait_for

BASE = "http://gluetun:8080"


def _login(password: str, user: str) -> Api | None:
    api = Api(f"{BASE}/api/v2", {"Referer": BASE})
    r = api.s.post(f"{BASE}/api/v2/auth/login", data={"username": user, "password": password}, timeout=15)
    # qBit 4.x: 200 "Ok." + SID cookie; 5.x: 204 + QBT_SID_<port> cookie
    has_session = any("SID" in c.name for c in api.s.cookies)
    return api if r.ok and r.text.strip() != "Fails." and has_session else None


def configure(ctx: Ctx):
    Log.section("qbittorrent")
    if not wait_for(f"{BASE}/api/v2/app/version", timeout=180):
        Log.warn("qBittorrent not reachable (is the VPN up? `docker compose logs gluetun`), skipping")
        return
    api = None
    for pw in filter(None, [ctx.previous_password, ctx.password]):
        api = _login(pw, ctx.user)
        if api:
            break
    if not api:
        Log.warn("qBittorrent: admin login rejected — was the password changed in its UI? "
                 "Set it back or delete config/qbittorrent/qBittorrent/qBittorrent.conf and re-run.")
        return

    cfg = ctx.cfg["qbittorrent"]
    prefs = api.get("/app/preferences")
    want = dict(cfg.get("preferences", {}))
    want["web_ui_username"] = ctx.user
    drift = {k: v for k, v in want.items() if prefs.get(k) != v}
    if ctx.password_changed:
        drift["web_ui_password"] = ctx.password
    if drift:
        shown = ", ".join(f"{k}={'***' if 'password' in k else v}" for k, v in drift.items())
        ctx.apply(f"qbittorrent: preferences {shown}",
                  lambda: api.post("/app/setPreferences", data={"json": json.dumps(drift)}))

    cats = api.get("/torrents/categories") or {}
    for name, path in cfg.get("categories", {}).items():
        cur = cats.get(name)
        if cur is None:
            ctx.apply(f"qbittorrent: category {name} -> {path}",
                      lambda n=name, p=path: api.post("/torrents/createCategory", data={"category": n, "savePath": p}))
        elif cur.get("savePath", "").rstrip("/") != path.rstrip("/"):
            ctx.apply(f"qbittorrent: category {name} path {cur.get('savePath')!r} -> {path}",
                      lambda n=name, p=path: api.post("/torrents/editCategory", data={"category": n, "savePath": p}))


