"""Shared plumbing: config loading, logging, HTTP, change tracking, files."""
import copy
import hashlib
import os
import secrets
import time
from pathlib import Path

import requests
import yaml

CONFIG = Path("/config")          # ./config on the host
STACK = Path("/stack")            # ./stack (read-only, committed)
LOCAL = Path("/local")            # ./local (read-only, gitignored)
DATA = Path("/data")              # ${MEDIA_ROOT}
PLEX = Path("/plex")              # plex_config volume (read-only)

CREDENTIALS = CONFIG / "stack" / "credentials.env"


# --------------------------------------------------------------------- logging
class Log:
    warnings: list[str] = []

    @staticmethod
    def section(name):
        print(f"\n== {name}", flush=True)

    @staticmethod
    def info(msg):
        print(f"   {msg}", flush=True)

    @staticmethod
    def change(msg):
        print(f" + {msg}", flush=True)

    @classmethod
    def warn(cls, msg):
        cls.warnings.append(msg)
        print(f" ! {msg}", flush=True)


class Ctx:
    """Carries run-wide state. `apply()` is the only place that mutates apps."""

    def __init__(self, dry_run: bool):
        self.dry_run = dry_run
        self.cfg = load_stack_config()
        self.keys: dict[str, str] = {}       # app -> api key
        self.plex: dict | None = None        # token, machine id, name
        self.user, self.password, self.password_changed, self.previous_password = load_credentials()
        self.changes = 0

    def apply(self, description: str, fn=None):
        """Record a change; run it unless this is a dry run."""
        self.changes += 1
        if self.dry_run:
            Log.change(f"[dry-run] {description}")
            return None
        Log.change(description)
        return fn() if fn else None


# ---------------------------------------------------------------------- config
def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_stack_config() -> dict:
    cfg = yaml.safe_load((STACK / "stack.yml").read_text()) or {}
    local = LOCAL / "stack.yml"
    if local.is_file():
        cfg = deep_merge(cfg, yaml.safe_load(local.read_text()) or {})
    return cfg


# ----------------------------------------------------------------- credentials
def read_env_file(path: Path) -> dict:
    out = {}
    if path.is_file():
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def write_private(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    os.chmod(path, 0o600)
    chown(path)


def load_credentials():
    """Return (user, desired_password, changed?, previously_applied_password).

    credentials.env always holds the password that is currently applied to the
    apps; ADMIN_PASSWORD in .env, if set, is the desired one.
    """
    stored = read_env_file(CREDENTIALS)
    user = os.environ.get("ADMIN_USER") or stored.get("ADMIN_USER") or "admin"
    applied = stored.get("ADMIN_PASSWORD")
    desired = os.environ.get("ADMIN_PASSWORD") or applied or secrets.token_urlsafe(18)
    changed = applied is not None and desired != applied
    return user, desired, changed, applied


def save_credentials(user: str, password: str):
    write_private(
        CREDENTIALS,
        "# Login for every web UI. Generated/managed by stack-init.\n"
        f"ADMIN_USER={user}\nADMIN_PASSWORD={password}\n",
    )


def md5(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()


# ----------------------------------------------------------------------- files
def chown(path: Path):
    """Hand files we create to PUID:PGID (matters on Linux hosts)."""
    try:
        os.chown(path, int(os.environ.get("PUID", 1000)), int(os.environ.get("PGID", 1000)))
    except (OSError, ValueError):
        pass


def write_if_changed(ctx: Ctx, path: Path, text: str, label: str, private=True) -> bool:
    if path.is_file() and path.read_text() == text:
        return False
    ctx.apply(f"write {label}", lambda: write_private(path, text) if private else _write(path, text))
    return True


def _write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    chown(path)


# ------------------------------------------------------------------------ http
class Api:
    def __init__(self, base: str, headers: dict | None = None, timeout=30):
        self.base = base.rstrip("/")
        self.s = requests.Session()
        self.s.headers.update(headers or {})
        self.timeout = timeout

    def req(self, method, path, **kw):
        r = self.s.request(method, f"{self.base}{path}", timeout=self.timeout, **kw)
        if r.status_code >= 400:
            raise ApiError(f"{method} {path} -> {r.status_code}: {r.text[:300]}")
        if not r.content:
            return None
        try:
            return r.json()
        except ValueError:
            return r.text

    def get(self, path, **kw):
        return self.req("GET", path, **kw)

    def post(self, path, **kw):
        return self.req("POST", path, **kw)

    def put(self, path, **kw):
        return self.req("PUT", path, **kw)

    def delete(self, path, **kw):
        return self.req("DELETE", path, **kw)


class ApiError(RuntimeError):
    pass


def wait_for(url: str, timeout=300, ok=lambda r: r.status_code < 500) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if ok(requests.get(url, timeout=5)):
                return True
        except requests.RequestException:
            pass
        time.sleep(3)
    return False


def reachable(url: str) -> bool:
    try:
        requests.get(url, timeout=3)
        return True
    except requests.RequestException:
        return False
