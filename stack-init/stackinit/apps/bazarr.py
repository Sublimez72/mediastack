"""Bazarr: login, Sonarr/Radarr connections, language profile, providers."""
import json
import os

import yaml

from ..common import CONFIG, Api, Ctx, Log, md5, wait_for

BASE = "http://bazarr:6767"


def _api_key():
    f = CONFIG / "bazarr" / "config" / "config.yaml"
    if f.is_file():
        return ((yaml.safe_load(f.read_text()) or {}).get("auth") or {}).get("apikey")
    return None


def configure(ctx: Ctx):
    Log.section("bazarr")
    if not wait_for(BASE, timeout=300):
        Log.warn("bazarr did not come up, skipping")
        return
    key = _api_key()
    if not key:
        Log.warn("bazarr: no API key in config.yaml yet, skipping")
        return
    ctx.keys["bazarr"] = key
    api = Api(f"{BASE}/api", {"X-API-KEY": key})
    cur = api.get("/system/settings")
    cfg = ctx.cfg["bazarr"]

    want: dict[str, object] = {
        "auth.type": "form",
        "auth.username": ctx.user,
        "general.use_sonarr": True,
        "general.use_radarr": True,
        "general.serie_default_enabled": True,
        "general.serie_default_profile": 1,
        "general.movie_default_enabled": True,
        "general.movie_default_profile": 1,
    }
    for app, port in (("sonarr", 8989), ("radarr", 7878)):
        if app in ctx.keys:
            want |= {f"{app}.ip": app, f"{app}.port": port, f"{app}.base_url": "", f"{app}.ssl": False,
                     f"{app}.apikey": ctx.keys[app]}
    want |= cfg.get("settings", {})

    providers = list(cfg.get("providers", []))
    if "opensubtitlescom" in providers:
        u, p = os.environ.get("OPENSUBTITLES_USERNAME"), os.environ.get("OPENSUBTITLES_PASSWORD")
        if u and p:
            want |= {"opensubtitlescom.username": u, "opensubtitlescom.password": p}
        else:
            providers.remove("opensubtitlescom")
            Log.info("opensubtitles.com skipped (no OPENSUBTITLES_USERNAME/PASSWORD)")

    drift = {k: v for k, v in want.items() if _get(cur, k) != v}
    if sorted(_get(cur, "general.enabled_providers") or []) != sorted(providers):
        drift["general.enabled_providers"] = providers
    form = [(f"settings-{k.replace('.', '-')}", _fmt(v)) for k, v in drift.items() if not isinstance(v, list)]
    for k, v in drift.items():
        if isinstance(v, list):
            form += [(f"settings-{k.replace('.', '-')}", x) for x in v] or [(f"settings-{k.replace('.', '-')}", "")]

    if _get(cur, "auth.password") != md5(ctx.password):
        form.append(("settings-auth-password", ctx.password))
        drift["auth.password"] = "***"

    langs = cfg.get("languages") or ["en"]
    profiles = api.get("/system/languages/profiles")
    enabled = sorted(l["code2"] for l in api.get("/system/languages", params={"history": "false"}) if l["enabled"])
    profile = {
        "profileId": 1, "name": "Default", "cutoff": None, "mustContain": [], "mustNotContain": [],
        "originalFormat": 0, "tag": None,
        "items": [{"id": i + 1, "language": c, "audio_exclude": "False", "audio_only_include": "False",
                   "hi": "False", "forced": "False"} for i, c in enumerate(langs)],
    }
    if not profiles:   # only create the default profile; never clobber a hand-tuned one
        form.append(("languages-profiles", json.dumps([profile])))
        drift["language profile"] = "Default"
    if enabled != sorted(langs) and not profiles:
        form += [("languages-enabled", c) for c in langs]
        drift["languages"] = langs

    if drift:
        ctx.apply("bazarr: " + ", ".join(f"{k}={'***' if 'password' in k or 'apikey' in k else v}"
                                         for k, v in drift.items()),
                  lambda: api.post("/system/settings", data=form))


def _get(d, dotted):
    for part in dotted.split("."):
        if not isinstance(d, dict):
            return None
        d = d.get(part)
    return d


def _fmt(v):
    return str(v).lower() if isinstance(v, bool) else str(v)
