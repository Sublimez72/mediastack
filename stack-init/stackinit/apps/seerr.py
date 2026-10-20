"""Seerr: first-run setup without the wizard, then keep Radarr/Sonarr wiring in sync."""
import json

from ..common import CONFIG, Api, Ctx, Log, enabled, wait_for
from . import jellyfin

BASE = "http://seerr:5055/api/v1"
SETTINGS = CONFIG / "seerr" / "settings.json"
ARRS = {"radarr": 7878, "sonarr": 8989}
SERVER_TYPES = {"plex": 1, "jellyfin": 2, "emby": 3}   # Seerr's MediaServerType; also the "auto" order
SERVER_NAMES = {"plex": "Plex", **jellyfin.SERVERS}


def configure(ctx: Ctx):
    Log.section("seerr")
    if not wait_for(f"{BASE}/settings/public", timeout=300):
        Log.warn("seerr did not come up, skipping")
        return
    public = Api(BASE).get("/settings/public")
    initialized = public.get("initialized")
    server = _server(ctx, public)

    if not initialized:
        if not server:
            return
        if server == "plex":
            # Creates the admin user from the Plex account that owns the server.
            ctx.apply("seerr: create admin from the Plex server owner",
                      lambda: Api(BASE).post("/auth/plex", json={"authToken": ctx.plex["token"]}))
        else:
            # Creates the admin user from the shared admin login on Jellyfin/Emby.
            ctx.apply(f"seerr: create admin from {jellyfin.SERVERS[server]} user '{ctx.user}'",
                      lambda: Api(BASE).post("/auth/jellyfin", json={
                          "username": ctx.user, "password": ctx.password, "hostname": server,
                          "port": jellyfin.PORT, "useSsl": False, "urlBase": "", "serverType": SERVER_TYPES[server]}))
        if ctx.dry_run:
            Log.info("(rest of first-run setup follows once the admin exists)")
            return
    key = _api_key()
    if not key:
        Log.warn("seerr: no API key in settings.json yet, skipping")
        return
    api = Api(BASE, {"X-Api-Key": key})

    if server == "plex":
        _plex(ctx, api, initialized)
    elif server:
        _jellyfin(ctx, api, server, initialized)
    for app in ARRS:
        if app in ctx.keys:
            _arr(ctx, api, app)

    if not initialized:
        sync = "plex" if server == "plex" else "jellyfin"   # Seerr's Emby settings live under "jellyfin" too
        ctx.apply("seerr: finish setup", lambda: api.post("/settings/initialize"))
        ctx.apply(f"seerr: start first {SERVER_NAMES[server]} library scan",
                  lambda: api.post(f"/settings/{sync}/sync", json={"start": True}))


def _server(ctx, public) -> str | None:
    """The one media server Seerr is linked to (Seerr supports only one).

    Picked at first setup: seerr.media_server in stack.yml, or else Plex if it's
    switched on, then Jellyfin, then Emby. After setup it's whatever Seerr has."""
    current = {v: k for k, v in SERVER_TYPES.items()}.get(public.get("mediaServerType"))
    wanted = ctx.cfg["seerr"].get("media_server") or "auto"
    if current:
        if wanted not in ("auto", current):
            Log.warn(f"seerr: already linked to {SERVER_NAMES[current]}; seerr.media_server={wanted} only "
                     "applies to a fresh Seerr (README > Media servers)")
        return current if _ready(ctx, current) else None
    if wanted == "auto":
        wanted = next((s for s in SERVER_TYPES if enabled(s)), None)
        if not wanted:
            Log.warn("seerr: no media server is switched on, setup waits")
            return None
    if wanted not in SERVER_TYPES:
        Log.warn(f"seerr: media_server '{wanted}' is not one of {', '.join(SERVER_TYPES)}")
        return None
    if not _ready(ctx, wanted):
        others = [SERVER_NAMES[s] for s in SERVER_TYPES if s != wanted and _ready(ctx, s)]
        hint = f"; or link it to {' / '.join(others)} with seerr.media_server in local/stack.yml" if others else ""
        Log.warn(f"seerr: waiting for {SERVER_NAMES[wanted]} to be set up before setup "
                 f"(it stays offline to the internet until then){hint}")
        return None
    return wanted


def _ready(ctx, server) -> bool:
    return bool(ctx.plex) if server == "plex" else server in ctx.media


def _api_key():
    try:
        return json.loads(SETTINGS.read_text())["main"]["apiKey"]
    except (OSError, ValueError, KeyError):
        return None


def _plex(ctx, api, initialized):
    cur = api.get("/settings/plex")
    want = {"ip": "plex", "port": 32400, "useSsl": False}
    if any(cur.get(k) != v for k, v in want.items()):
        ctx.apply(f"seerr: Plex server -> plex:32400 (was {cur.get('ip')}:{cur.get('port')})",
                  lambda: api.post("/settings/plex", json=want))
    if not initialized:
        def enable_libraries():
            for lib in api.post("/settings/plex/library/sync") or []:
                api.put(f"/settings/plex/library/{lib['id']}", json={"enabled": True})
        ctx.apply("seerr: enable all Plex libraries", enable_libraries)


def _jellyfin(ctx, api, server, initialized):
    cur = api.get("/settings/jellyfin")
    want = {"ip": server, "port": jellyfin.PORT, "useSsl": False, "urlBase": ""}
    if any(cur.get(k) != v for k, v in want.items()):
        ctx.apply(f"seerr: {SERVER_NAMES[server]} server -> {server}:{jellyfin.PORT} (was {cur.get('ip')}:{cur.get('port')})",
                  lambda: api.post("/settings/jellyfin", json=want))
    if not initialized:
        def enable_libraries():
            for lib in api.post("/settings/jellyfin/library/sync") or []:
                api.put(f"/settings/jellyfin/library/{lib['id']}", json={"enabled": True})
        ctx.apply(f"seerr: enable all {SERVER_NAMES[server]} libraries", enable_libraries)


def _arr(ctx, api, app):
    cfg = ctx.cfg["seerr"][app]
    port = ARRS[app]
    conn = {"hostname": app, "port": port, "apiKey": ctx.keys[app], "useSsl": False, "baseUrl": ""}
    probe = api.post(f"/settings/{app}/test", json=conn)
    profiles = {p["name"]: p["id"] for p in probe["profiles"]}

    def profile(name):
        if name in profiles:
            return profiles[name]
        Log.warn(f"seerr: {app} profile '{name}' not found (have: {', '.join(profiles)}) — using the first one")
        return next(iter(profiles.values()))

    want = conn | {
        "name": app.capitalize(), "is4k": False, "isDefault": True,
        "activeProfileId": profile(cfg["profile"]), "activeProfileName": cfg["profile"],
        "activeDirectory": cfg["root_folder"], "syncEnabled": True, "preventSearch": False,
    }
    if app == "radarr":
        want["minimumAvailability"] = cfg.get("minimum_availability", "released")
    else:
        anime = cfg.get("anime_profile") or cfg["profile"]
        want |= {"activeAnimeProfileId": profile(anime), "activeAnimeProfileName": anime,
                 "activeAnimeDirectory": cfg.get("anime_root_folder") or cfg["root_folder"],
                 "enableSeasonFolders": True}
    if not probe["profiles"]:
        Log.warn(f"seerr: {app} has no quality profiles yet, skipping")
        return

    servers = [s for s in api.get(f"/settings/{app}") if not s.get("is4k")]
    match = next((s for s in servers if s["hostname"] == app), servers[0] if servers else None)
    if match:
        drift = {k: v for k, v in want.items() if k != "name" and match.get(k) != v}
        if not drift:
            return
        merged = {k: v for k, v in match.items() if k != "id"} | drift   # Seerr rejects a body with "id"
        shown = ", ".join(f"{k}={'***' if k == 'apiKey' else v}" for k, v in drift.items())
        ctx.apply(f"seerr: {app} server {shown}", lambda: api.put(f"/settings/{app}/{match['id']}", json=merged))
    else:
        ctx.apply(f"seerr: add {app} server", lambda: api.post(f"/settings/{app}", json=want))
