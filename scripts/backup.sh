#!/usr/bin/env bash
# Snapshot everything settings-as-code can't rebuild: watch/request history,
# Plex/Jellyfin/Emby metadata, app databases. Run nightly (cron) — keeps the last $KEEP.
#   scripts/backup.sh [backup_dir]        (default: ./backups)
set -euo pipefail
cd "$(dirname "$0")/.."
dest=${1:-${BACKUP_DIR:-./backups}}
keep=${KEEP:-14}
stamp=$(date +%Y-%m-%d_%H%M)
out="$dest/mediastack-$stamp"
mkdir -p "$out"

# *arr apps write consistent zips on their own schedule; take the newest of each
for app in sonarr radarr prowlarr; do
  latest=$(ls -t config/$app/Backups/scheduled/*.zip 2>/dev/null | head -1 || true)
  [ -n "$latest" ] && cp "$latest" "$out/$app.zip"
done
latest=$(ls -t config/bazarr/backup/*.zip 2>/dev/null | head -1 || true)
[ -n "$latest" ] && cp "$latest" "$out/bazarr.zip"

# SQLite apps: copy while briefly stopped so the DB files are consistent
running() { docker compose ps --services --status running 2>/dev/null | grep -qx "$1"; }
for app in seerr tautulli; do
  [ -d "config/$app" ] || continue
  was_running=; running "$app" && was_running=1 && docker compose stop "$app" >/dev/null
  tar --exclude="$app/logs" --exclude="$app/cache" -czf "$out/$app.tgz" -C config "$app"
  [ -n "$was_running" ] && docker compose start "$app" >/dev/null
done

# Media servers (named volumes): whichever exist. Skip regenerable caches.
project="${COMPOSE_PROJECT_NAME:-mediastack}"
found=
for server in plex jellyfin emby; do
  vol="${project}_${server}_config"
  docker volume inspect "$vol" >/dev/null 2>&1 || continue
  found=1
  case $server in
    plex) skip='./Library/Application Support/Plex Media Server/Cache' ;;
    *)    skip='./cache' ;;
  esac
  was_running=; running "$server" && was_running=1 && docker compose stop "$server" >/dev/null
  docker run --rm -v "$vol":/src:ro -v "$(realpath "$out")":/out alpine \
    tar --exclude="$skip" -czf "/out/$server.tgz" -C /src .
  [ -n "$was_running" ] && docker compose start "$server" >/dev/null
done
[ -n "$found" ] || { echo "no media server volume found (${project}_plex_config etc.; set COMPOSE_PROJECT_NAME?)" >&2; exit 1; }

# your settings (contains secrets — keep the backup dir private)
cp .env "$out/env" 2>/dev/null || true
[ -d local ] && tar -czf "$out/local.tgz" local
cp config/stack/credentials.env "$out/" 2>/dev/null || true

ls -1dt "$dest"/mediastack-* | tail -n +$((keep + 1)) | xargs -r rm -rf
echo "backup written to $out"
