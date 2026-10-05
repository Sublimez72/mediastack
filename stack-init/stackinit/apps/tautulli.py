"""Tautulli: seeded via config.ini before its first start.

Tautulli has no settings API that is safe to call partially, and it rewrites
config.ini on shutdown, so we only write the file while it isn't running.
(compose starts Tautulli after stack-init, so the first `up` always qualifies.)
"""
import base64
import configparser
import hashlib
import io
import os
import secrets

from ..common import CONFIG, Ctx, Log, reachable, write_private

INI = CONFIG / "tautulli" / "config.ini"
CONFIG_VERSION = 22   # Tautulli's current config schema; skips its upgrade migrations


def _hash(password: str) -> str:
    """Same format as Tautulli's lib/hashing_passwords.make_hash."""
    salt = base64.b64encode(os.urandom(16))
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000, 24)
    return f"PBKDF2$sha256$600000${salt.decode()}${base64.b64encode(key).decode()}"


def configure(ctx: Ctx):
    Log.section("tautulli")
    ini = configparser.ConfigParser(interpolation=None)
    ini.optionxform = str
    if INI.is_file():
        ini.read(INI)
    has_login = bool(ini.get("General", "http_password", fallback="").strip('"'))
    has_plex = bool(ini.get("PMS", "pms_token", fallback="").strip('"'))
    todo = []
    if not has_login:
        todo.append("admin login")
    if not has_plex and ctx.plex:
        todo.append(f"connect to Plex ({ctx.plex['name']})")
    if not todo:
        Log.info("already set up" if has_plex else "login set; waiting for a claimed Plex server")
        return
    if reachable("http://tautulli:8181"):
        Log.warn(f"tautulli is running, so it can't be configured ({', '.join(todo)}). Run "
                 "`docker compose stop tautulli` then `docker compose up -d`.")
        return

    for section in ("General", "PMS", "Advanced"):
        if not ini.has_section(section):
            ini.add_section(section)
    if not has_login:
        for k, v in {
            "http_username": ctx.user,
            "http_password": _hash(ctx.password),
            "http_hash_password": "1",
            "http_hashed_password": "1",
            "http_plex_admin": "1",
            "api_enabled": "1",
            "api_key": ini.get("General", "api_key", fallback="") or secrets.token_hex(16),
        }.items():
            ini.set("General", k, v)
    if not has_plex and ctx.plex:
        ini.set("General", "first_run_complete", "1")
        for k, v in {
            "pms_ip": "plex", "pms_port": "32400", "pms_ssl": "0", "pms_is_remote": "0",
            "pms_url": "http://plex:32400", "pms_url_manual": "1",
            "pms_token": ctx.plex["token"], "pms_identifier": ctx.plex["machine_id"], "pms_name": ctx.plex["name"],
        }.items():
            ini.set("PMS", k, v)
    if not ini.get("Advanced", "config_version", fallback=""):
        ini.set("Advanced", "config_version", str(CONFIG_VERSION))

    def write():
        buf = io.StringIO()
        ini.write(buf)
        write_private(INI, buf.getvalue())
    ctx.apply("tautulli: " + " + ".join(todo), write)
