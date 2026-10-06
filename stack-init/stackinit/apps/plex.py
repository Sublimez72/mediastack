"""Plex: discover token from the claimed server, create libraries, LAN prefs."""
import os
import time
import xml.etree.ElementTree as ET

from ..common import PLEX, Api, Ctx, Log

PREFS = PLEX / "Library" / "Application Support" / "Plex Media Server" / "Preferences.xml"
BASE = "http://plex:32400"
AGENTS = {
    "movie": ("tv.plex.agents.movie", "Plex Movie"),
    "show": ("tv.plex.agents.series", "Plex TV Series"),
}


def discover(ctx: Ctx):
    """Fill ctx.plex from Preferences.xml. Waits for a pending claim to land."""
    Log.section("plex")
    deadline = time.time() + (300 if os.environ.get("PLEX_CLAIM") else 20)
    while True:
        attrs = _prefs()
        if attrs.get("PlexOnlineToken"):
            ctx.plex = {"token": attrs["PlexOnlineToken"], "machine_id": attrs.get("ProcessedMachineIdentifier", ""),
                        "name": attrs.get("FriendlyName", "Plex")}
            Log.info(f"claimed server found ({ctx.plex['name']})")
            return
        if time.time() > deadline:
            Log.warn("Plex is not claimed — set PLEX_CLAIM in .env (https://plex.tv/claim) and run "
                     "`docker compose up -d` again. Plex-dependent wiring (Seerr, Tautulli, library updates) skipped.")
            return
        time.sleep(5)


def _prefs() -> dict:
    try:
        return ET.parse(PREFS).getroot().attrib
    except (OSError, ET.ParseError):
        return {}


def configure(ctx: Ctx):
    if not ctx.plex:
        return
    api = Api(BASE, {"X-Plex-Token": ctx.plex["token"], "Accept": "application/json"})
    sections = api.get("/library/sections")["MediaContainer"].get("Directory", [])
    used = {loc["path"].rstrip("/") for s in sections for loc in s.get("Location", [])}
    for lib in ctx.cfg["plex"].get("libraries", []):
        if lib["path"].rstrip("/") in used:
            continue
        agent, scanner = AGENTS[lib["type"]]
        params = {"name": lib["name"], "type": lib["type"], "agent": agent, "scanner": scanner,
                  "language": lib.get("language", "en-US"), "location": lib["path"]}
        ctx.apply(f"plex: library '{lib['name']}' -> {lib['path']}",
                  lambda p=params: api.post("/library/sections", params=p))

    want = dict(ctx.cfg["plex"].get("preferences", {}))
    want["FriendlyName"] = os.environ.get("PLEX_SERVER_NAME") or "mediastack"
    if want:
        cur = {s["id"]: s.get("value") for s in api.get("/:/prefs")["MediaContainer"].get("Setting", [])}
        drift = {k: v for k, v in want.items() if str(cur.get(k)) != str(v)}
        if drift:
            ctx.apply("plex: preferences " + ", ".join(f"{k}={v}" for k, v in drift.items()),
                      lambda: api.put("/:/prefs", params=drift))
