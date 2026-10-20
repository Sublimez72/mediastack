"""`apply`: wire every app together from stack.yml. Safe to run repeatedly."""
import os
import traceback

from .apps import arr, bazarr, generated, jellyfin, plex, prowlarr, qbittorrent, sabnzbd, seerr, tautulli
from .common import Ctx, Log, enabled, save_credentials

UIS = [("Seerr (requests)", 5055), ("Sonarr", 8989), ("Radarr", 7878), ("Prowlarr", 9696),
       ("Bazarr", 6767), ("qBittorrent", 8080), ("Tautulli", 8181)]
MEDIA_UIS = [("jellyfin", "Jellyfin", 8096), ("emby", "Emby", 8097)]   # host ports from compose.yml


def run(dry_run=False) -> int:
    ctx = Ctx(dry_run)
    if dry_run:
        print("DRY RUN — nothing will be changed")

    steps = [
        lambda: sabnzbd.configure(ctx),         # before Sonarr/Radarr, which need its API key
        lambda: arr.configure(ctx, "sonarr"),
        lambda: arr.configure(ctx, "radarr"),
        lambda: prowlarr.configure(ctx),
        lambda: qbittorrent.configure(ctx),
        lambda: generated.recyclarr(ctx),       # quality profiles before Seerr picks defaults
        lambda: bazarr.configure(ctx),
        lambda: plex.discover(ctx),
        lambda: plex.configure(ctx),
        lambda: jellyfin.configure(ctx, "jellyfin"),
        lambda: jellyfin.configure(ctx, "emby"),
        lambda: arr.plex_notification(ctx, "sonarr"),
        lambda: arr.plex_notification(ctx, "radarr"),
        *[lambda a=a, s=s: arr.media_notification(ctx, a, s)
          for a in ("sonarr", "radarr") for s in jellyfin.SERVERS],
        lambda: seerr.configure(ctx),
        lambda: tautulli.configure(ctx) if enabled("plex") else None,   # Tautulli is switched off with Plex
        lambda: generated.decluttarr(ctx),
    ]
    failed = False
    for step in steps:
        try:
            step()
        except Exception as e:  # keep going: one broken app shouldn't block the rest
            failed = True
            Log.warn(f"step failed: {e}")
            traceback.print_exc()

    if not dry_run and ctx.password_changed and not failed:  # retry everything next run if not
        save_credentials(ctx.user, ctx.password)

    _summary(ctx)
    # Only a broken core (no Sonarr/Radarr) blocks the containers that depend on
    # stack-init; anything else is reported above and retried on the next `up`.
    return 1 if "sonarr" not in ctx.keys or "radarr" not in ctx.keys else 0


def _summary(ctx):
    print("\n" + "=" * 60)
    print(f"{'would change' if ctx.dry_run else 'changes applied'}: {ctx.changes}")
    if Log.warnings:
        print(f"warnings ({len(Log.warnings)}):")
        for w in Log.warnings:
            print(f"  - {w}")
    host = os.environ.get("BIND_ADDR", "127.0.0.1")
    host = "localhost" if host in ("127.0.0.1", "0.0.0.0") else host
    print("\nweb UIs (login: user/password in config/stack/credentials.env):")
    uis = UIS + [("SABnzbd (Usenet)", 8085)] if sabnzbd.enabled() else UIS
    for name, port in uis:
        if name != "Tautulli" or enabled("plex"):
            print(f"  {name:<18} http://{host}:{port}")
    if enabled("plex"):
        print("  Plex               https://app.plex.tv")
    for service, name, port in MEDIA_UIS:
        if enabled(service):
            print(f"  {name:<18} http://{host}:{port}")
    print("=" * 60)
