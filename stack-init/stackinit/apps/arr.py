"""Sonarr / Radarr (and the shared *arr bits Prowlarr reuses)."""
import re

from ..common import CONFIG, Api, Ctx, Log, wait_for

ARRS = {
    "sonarr": {"port": 8989, "api": "v3", "category_field": "tvCategory"},
    "radarr": {"port": 7878, "api": "v3", "category_field": "movieCategory"},
    "prowlarr": {"port": 9696, "api": "v1"},
}
QBIT_NAME = "qBittorrent"   # decluttarr matches download clients by this name


def api_key(app: str) -> str | None:
    xml = CONFIG / app / "config.xml"
    if not xml.is_file():
        return None
    m = re.search(r"<ApiKey>([^<]+)</ApiKey>", xml.read_text())
    return m.group(1) if m else None


def client(ctx: Ctx, app: str) -> Api | None:
    meta = ARRS[app]
    base = f"http://{app}:{meta['port']}"
    if not wait_for(f"{base}/ping", timeout=300):
        Log.warn(f"{app} did not come up, skipping")
        return None
    key = api_key(app)
    if not key:
        Log.warn(f"{app}: no API key in config.xml yet, skipping")
        return None
    ctx.keys[app] = key
    return Api(f"{base}/api/{meta['api']}", {"X-Api-Key": key}, timeout=180)


def field_map(resource: dict) -> dict:
    return {f["name"]: f.get("value") for f in resource.get("fields", [])}


def differs(current, wanted) -> bool:
    """*arr APIs return secrets as '********'; treat those as unchanged."""
    if isinstance(current, str) and current and set(current) == {"*"}:
        return False
    return current != wanted


def set_fields(resource: dict, values: dict) -> dict:
    for f in resource["fields"]:
        if f["name"] in values:
            f["value"] = values[f["name"]]
    return resource


# ------------------------------------------------------------------ shared
def ensure_auth(ctx: Ctx, app: str, api: Api):
    host = api.get("/config/host")
    want = {"authenticationMethod": "forms", "authenticationRequired": "enabled", "username": ctx.user}
    if all(str(host.get(k, "")).lower() == v.lower() for k, v in want.items()) and host.get("password") \
            and not ctx.password_changed:
        return
    host.update(want, password=ctx.password, passwordConfirmation=ctx.password)
    ctx.apply(f"{app}: login required (forms, user '{ctx.user}')",
              lambda: api.put(f"/config/host/{host['id']}", json=host))


# ------------------------------------------------------------ sonarr/radarr
def configure(ctx: Ctx, app: str):
    Log.section(app)
    api = client(ctx, app)
    if not api:
        return
    cfg = ctx.cfg[app]
    ensure_auth(ctx, app, api)
    _root_folders(ctx, app, api, cfg["root_folders"])
    _download_client(ctx, app, api, cfg["category"])
    if cfg.get("remove_remote_path_mappings"):
        for m in api.get("/remotepathmapping"):
            ctx.apply(f"{app}: remove remote path mapping {m['remotePath']} -> {m['localPath']}",
                      lambda m=m: api.delete(f"/remotepathmapping/{m['id']}"))
    _patch(ctx, app, api, "/config/mediamanagement", cfg.get("media_management", {}), "media management")
    for dp in api.get("/delayprofile"):
        if dp.get("order") == 2147483647:   # the default profile
            _patch_obj(ctx, app, api, f"/delayprofile/{dp['id']}", dp, cfg.get("delay_profile", {}), "delay profile")


def _root_folders(ctx, app, api, wanted):
    have = {r["path"].rstrip("/") for r in api.get("/rootfolder")}
    for path in wanted:
        if path.rstrip("/") not in have:
            ctx.apply(f"{app}: add root folder {path}", lambda p=path: api.post("/rootfolder", json={"path": p}))


def _download_client(ctx, app, api, category):
    cat_field = ARRS[app]["category_field"]
    want = {"host": "gluetun", "port": 8080, "useSsl": False, "username": ctx.user, cat_field: category}
    existing = [c for c in api.get("/downloadclient") if c["implementation"] == "QBittorrent"]
    if existing:
        dc = existing[0]
        cur = field_map(dc)
        drift = {k: v for k, v in want.items() if differs(cur.get(k), v)}
        flags_ok = dc.get("enable") and dc.get("removeCompletedDownloads") and dc.get("removeFailedDownloads") \
            and dc["name"] == QBIT_NAME
        if not drift and flags_ok and not ctx.password_changed:
            return
        why = ", ".join(f"{k}={v}" for k, v in drift.items()) or "flags/password"
        method, path = "PUT", f"/downloadclient/{dc['id']}"
    else:
        dc = next(s for s in api.get("/downloadclient/schema") if s["implementation"] == "QBittorrent")
        why, method, path = "new", "POST", "/downloadclient"
    set_fields(dc, {**want, "password": ctx.password})
    dc.update(name=QBIT_NAME, enable=True, removeCompletedDownloads=True, removeFailedDownloads=True)
    ctx.apply(f"{app}: qBittorrent download client ({why})",
              lambda: api.req(method, path, params={"forceSave": "true"}, json=dc))


def _patch(ctx, app, api, path, wanted, label):
    if wanted:
        _patch_obj(ctx, app, api, path, api.get(path), wanted, label)


def _patch_obj(ctx, app, api, path, current, wanted, label):
    drift = {k: v for k, v in wanted.items() if current.get(k) != v}
    if not drift:
        return
    current.update(drift)
    target = path if path.rsplit("/", 1)[-1].isdigit() or "id" not in current else f"{path}/{current['id']}"
    ctx.apply(f"{app}: {label}: " + ", ".join(f"{k}={v}" for k, v in drift.items()),
              lambda: api.put(target, json=current))


# ---------------------------------------------------------- plex connect
def plex_notification(ctx: Ctx, app: str):
    if not ctx.plex or app not in ctx.keys:
        return
    api = Api(f"http://{app}:{ARRS[app]['port']}/api/v3", {"X-Api-Key": ctx.keys[app]})
    want = {"host": "plex", "port": 32400, "useSsl": False, "authToken": ctx.plex["token"], "updateLibrary": True}
    existing = [n for n in api.get("/notification") if n["implementation"] == "PlexServer"]
    if existing:
        n = existing[0]
        if not any(differs(field_map(n).get(k), v) for k, v in want.items()):
            return
        method, path, why = "PUT", f"/notification/{n['id']}", "update"
    else:
        n = next(s for s in api.get("/notification/schema") if s["implementation"] == "PlexServer")
        n["name"] = "Plex"
        # enable every event Plex supports (download, upgrade, rename, delete...)
        for k in list(n):
            if k.startswith("supportsOn") and n[k]:
                n["on" + k.removeprefix("supportsOn")] = True
        method, path, why = "POST", "/notification", "new"
    set_fields(n, want)
    ctx.apply(f"{app}: Plex library-update notification ({why})", lambda: api.req(method, path, json=n))
