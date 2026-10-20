"""Jellyfin and Emby: first-run wizard, admin login, API key, libraries, server name, GPU.

Jellyfin is a fork of Emby and the parts we use are the same API, so one module
serves both. Each is only configured when its compose profile is switched on.
"""
import os

from ..common import Api, ApiError, Ctx, Log, enabled, server_name, wait_for

SERVERS = {"jellyfin": "Jellyfin", "emby": "Emby"}
PORT = 8096                     # inside the container, for both
APP_NAME = "mediastack"         # name of the API key stack-init creates (and Sonarr/Radarr/Seerr use)
COLLECTION = {"movie": "movies", "show": "tvshows"}
CLIENT = 'MediaBrowser Client="mediastack", Device="stack-init", DeviceId="stack-init", Version="1.0"'


def base(app: str) -> str:
    return f"http://{app}:{PORT}"


def configure(ctx: Ctx, app: str):
    if not enabled(app):
        return
    Log.section(app)
    if not wait_for(f"{base(app)}/System/Info/Public", timeout=300, ok=lambda r: r.status_code == 200):
        Log.warn(f"{app} did not come up, skipping")
        return
    anon = Api(base(app), {"Authorization": CLIENT})

    if _wizard_pending(anon):
        ctx.apply(f"{app}: finish first-run setup, admin user '{ctx.user}'", lambda: _wizard(anon, ctx))
        if ctx.dry_run:
            Log.info("(libraries and the rest follow once the admin exists)")
            return

    token, user_id, pw = _login(ctx, app, anon)
    if not token:
        return
    api = Api(base(app), {"Authorization": f'{CLIENT}, Token="{token}"'})
    if pw != ctx.password:
        ctx.apply(f"{app}: admin password", lambda: api.post(
            f"/Users/{user_id}/Password", json={"CurrentPw": pw, "NewPw": ctx.password}))

    key = _api_key(ctx, app, api)
    if key:
        ctx.media[app] = {"key": key}
    _libraries(ctx, app, api)
    _server_name(ctx, app, api)
    if app == "jellyfin":
        _hardware(ctx, app, api)


def _wizard_pending(anon: Api) -> bool:
    """The Startup endpoints answer without a login only until the wizard is done."""
    try:
        anon.get("/Startup/User")
        return True
    except ApiError:
        return False


def _wizard(anon: Api, ctx: Ctx):
    anon.post("/Startup/Configuration", json={
        "ServerName": server_name(), "UICulture": "en-US",
        "MetadataCountryCode": "US", "PreferredMetadataLanguage": "en"})
    anon.post("/Startup/User", json={"Name": ctx.user, "Password": ctx.password})
    anon.post("/Startup/Complete")


def _login(ctx: Ctx, app: str, anon: Api):
    """Sign in as the shared admin. Tries the previous password too, so a new
    ADMIN_PASSWORD can be rolled out."""
    for pw in dict.fromkeys(p for p in (ctx.password, ctx.previous_password) if p is not None):
        try:
            r = anon.post("/Users/AuthenticateByName", json={"Username": ctx.user, "Pw": pw})
            return r["AccessToken"], r["User"]["Id"], pw
        except ApiError:
            continue
    Log.warn(f"{app}: can't sign in as '{ctx.user}' with the password in config/stack/credentials.env "
             f"(changed in {SERVERS[app]}'s settings?). {SERVERS[app]} wiring skipped.")
    return None, None, None


def _api_key(ctx: Ctx, app: str, api: Api) -> str | None:
    def find():
        return next((k["AccessToken"] for k in api.get("/Auth/Keys")["Items"] if k.get("AppName") == APP_NAME), None)
    key = find()
    if key:
        return key
    ctx.apply(f"{app}: create API key '{APP_NAME}'", lambda: api.post("/Auth/Keys", params={"App": APP_NAME}))
    return None if ctx.dry_run else find()


def _libraries(ctx: Ctx, app: str, api: Api):
    used = {loc.rstrip("/") for f in api.get("/Library/VirtualFolders") for loc in f.get("Locations", [])}
    for lib in ctx.cfg[app].get("libraries", []):
        if lib["path"].rstrip("/") in used:
            continue
        params = {"name": lib["name"], "collectionType": COLLECTION[lib["type"]], "refreshLibrary": "true"}
        # Metadata and artwork stay in the server's own config: nothing is written
        # next to the media, which Plex, the other server and Sonarr/Radarr all share.
        body = {"LibraryOptions": {"PathInfos": [{"Path": lib["path"]}], "SaveLocalMetadata": False,
                                   "MetadataSavers": [], "PreferredMetadataLanguage": lib.get("language", "en")}}
        ctx.apply(f"{app}: library '{lib['name']}' -> {lib['path']}",
                  lambda p=params, b=body: api.post("/Library/VirtualFolders", params=p, json=b))


def _server_name(ctx: Ctx, app: str, api: Api):
    want = server_name()
    conf = api.get("/System/Configuration")
    if conf.get("ServerName") != want:
        conf["ServerName"] = want
        ctx.apply(f"{app}: server name -> {want}", lambda: api.post("/System/Configuration", json=conf))


def _hardware(ctx: Ctx, app: str, api: Api):
    """Jellyfin only: Emby's hardware transcoding needs Emby Premiere and switches itself on."""
    gpu = os.environ.get("GPU", "")
    want = (ctx.cfg[app].get("hardware_acceleration") or {}).get(gpu)
    if not want:
        return
    conf = api.get("/System/Configuration/encoding")
    drift = {k: v for k, v in want.items() if conf.get(k) != v}
    if drift:
        conf.update(drift)
        ctx.apply(f"{app}: hardware transcoding ({gpu}): " + ", ".join(f"{k}={v}" for k, v in drift.items()),
                  lambda: api.post("/System/Configuration/encoding", json=conf))

