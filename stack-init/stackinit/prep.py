"""`prep`: runs before the apps start. Folders, admin login, qBittorrent seed."""
import base64
import hashlib
import os

from .common import CONFIG, DATA, Log, chown, load_credentials, load_stack_config, save_credentials, write_private

APP_DIRS = ["sonarr", "radarr", "prowlarr", "bazarr", "qbittorrent", "seerr", "tautulli",
            "recyclarr", "decluttarr", "tailscale", "stack"]


def run():
    cfg = load_stack_config()

    Log.section("folders")
    for d in [CONFIG / a for a in APP_DIRS] + [DATA / p.removeprefix("/data/") for p in _data_dirs(cfg)]:
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            Log.change(f"created {d}")
        chown(d)

    Log.section("admin login")
    user, password, _, applied = load_credentials()
    if applied is None:
        save_credentials(user, password)
        src = "ADMIN_PASSWORD from .env" if os.environ.get("ADMIN_PASSWORD") else "generated password"
        Log.change(f"stored {src} for user '{user}' in config/stack/credentials.env")
    else:
        Log.info("credentials already exist")

    Log.section("qbittorrent")
    _seed_qbittorrent(user, applied or password, cfg)


def _data_dirs(cfg):
    dirs = set(cfg["paths"].values())
    dirs.update(cfg["qbittorrent"]["categories"].values())
    for app in ("sonarr", "radarr"):
        dirs.update(cfg[app]["root_folders"])
        dirs.add(cfg[app].get("media_management", {}).get("recycleBin") or "")
    return sorted(d for d in dirs if d.startswith("/data/"))


def _qbit_hash(password: str) -> str:
    """qBittorrent's WebUI\\Password_PBKDF2 format."""
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha512", password.encode(), salt, 100_000, 64)
    return f"@ByteArray({base64.b64encode(salt).decode()}:{base64.b64encode(key).decode()})"


def _seed_qbittorrent(user, password, cfg):
    """Write qBittorrent.conf before first boot so the login is known up front
    (otherwise qBit generates a random temp password only visible in its logs).
    Everything else is applied later over the API."""
    conf = CONFIG / "qbittorrent" / "qBittorrent" / "qBittorrent.conf"
    if conf.exists():
        Log.info("qBittorrent.conf exists, leaving it to the API step")
        return
    downloads = cfg["paths"]["downloads"]
    write_private(conf, "\n".join([
        "[BitTorrent]",
        f"Session\\DefaultSavePath={downloads}",
        "Session\\DisableAutoTMMByDefault=false",
        "",
        "[LegalNotice]",
        "Accepted=true",
        "",
        "[Preferences]",
        f"Downloads\\SavePath={downloads}",
        f"WebUI\\Username={user}",
        f'WebUI\\Password_PBKDF2="{_qbit_hash(password)}"',
        "WebUI\\LocalHostAuth=false",
        "WebUI\\Port=8080",
        "",
    ]))
    chown(conf.parent)
    Log.change("seeded qBittorrent.conf with the admin login")
