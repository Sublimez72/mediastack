"""Prowlarr: auth, FlareSolverr, app sync to Sonarr/Radarr, public indexers."""
from ..common import ApiError, Ctx, Log
from .arr import client, differs, ensure_auth, field_map, set_fields

FS_TAG = "flaresolverr"


def configure(ctx: Ctx):
    Log.section("prowlarr")
    api = client(ctx, "prowlarr")
    if not api:
        return
    ensure_auth(ctx, "prowlarr", api)
    tag_id = _flaresolverr(ctx, api)
    for app, port in (("sonarr", 8989), ("radarr", 7878)):
        if app in ctx.keys:
            _application(ctx, api, app, port)
    _indexers(ctx, api, tag_id)


def _tag(ctx, api, label):
    for t in api.get("/tag"):
        if t["label"] == label:
            return t["id"]
    created = ctx.apply(f"prowlarr: create tag '{label}'", lambda: api.post("/tag", json={"label": label}))
    return created["id"] if created else -1


def _flaresolverr(ctx, api):
    tag_id = _tag(ctx, api, FS_TAG)
    want = {"host": "http://flaresolverr:8191/", "requestTimeout": 60}
    existing = [p for p in api.get("/indexerproxy") if p["implementation"] == "FlareSolverr"]
    if existing:
        p = existing[0]
        if not any(differs(field_map(p).get(k), v) for k, v in want.items()) and tag_id in p["tags"]:
            return tag_id
        method, path = "PUT", f"/indexerproxy/{p['id']}"
    else:
        p = next(s for s in api.get("/indexerproxy/schema") if s["implementation"] == "FlareSolverr")
        method, path = "POST", "/indexerproxy"
    set_fields(p, want)
    p.update(name="FlareSolverr", tags=sorted(set(p.get("tags", [])) | {tag_id}))
    ctx.apply("prowlarr: FlareSolverr proxy", lambda: api.req(method, path, params={"forceSave": "true"}, json=p))
    return tag_id


def _application(ctx, api, app, port):
    impl = app.capitalize()
    want = {"prowlarrUrl": "http://prowlarr:9696", "baseUrl": f"http://{app}:{port}", "apiKey": ctx.keys[app]}
    existing = [a for a in api.get("/applications") if a["implementation"] == impl]
    if existing:
        a = existing[0]
        if not any(differs(field_map(a).get(k), v) for k, v in want.items()) and a["syncLevel"] == "fullSync":
            return
        method, path, why = "PUT", f"/applications/{a['id']}", "update"
    else:
        a = next(s for s in api.get("/applications/schema") if s["implementation"] == impl)
        method, path, why = "POST", "/applications", "new"
    set_fields(a, want)
    a.update(name=impl, syncLevel="fullSync")
    ctx.apply(f"prowlarr: sync indexers to {impl} ({why})",
              lambda: api.req(method, path, params={"forceSave": "true"}, json=a))


def _indexers(ctx, api, tag_id):
    wanted = ctx.cfg["prowlarr"].get("indexers") or []
    if not wanted:
        return
    have = api.get("/indexer")
    have_names = {i["name"].lower() for i in have} | {str(i.get("definitionName", "")).lower() for i in have}
    missing = [w for w in wanted if w["name"].lower() not in have_names]
    if not missing:
        return
    schema = api.get("/indexer/schema")
    by_name = {s["name"].lower(): s for s in schema} | {str(s.get("definitionName", "")).lower(): s for s in schema}
    for w in missing:
        s = by_name.get(w["name"].lower())
        if not s:
            Log.warn(f"prowlarr: no indexer called '{w['name']}' in this Prowlarr version")
            continue
        s.update(enable=True, appProfileId=1, priority=25,
                 tags=[tag_id] if w.get("flaresolverr") and tag_id > 0 else [])
        try:
            ctx.apply(f"prowlarr: add indexer {s['name']}" + (" (via FlareSolverr)" if w.get("flaresolverr") else ""),
                      lambda s=s: api.post("/indexer", params={"forceSave": "true"}, json=s))
        except ApiError as e:
            # usually the site is down or blocked by your ISP; retried on the next run
            Log.warn(f"prowlarr: couldn't add {s['name']} (unreachable from here?): {str(e)[:160]}")
