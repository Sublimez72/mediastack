#!/usr/bin/env bash
# Snapshot everything settings-as-code can't rebuild: watch/request history,
# Plex metadata, app databases. Run nightly (cron) — keeps the last $KEEP.
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
docker compose stop seerr tautulli >/dev/null
tar --exclude='seerr/logs' --exclude='seerr/cache' -czf "$out/seerr.tgz" -C config seerr
tar --exclude='tautulli/logs' --exclude='tautulli/cache' -czf "$out/tautulli.tgz" -C config tautulli
docker compose start seerr tautulli >/dev/null

# Plex (named volume) — skip the regenerable cache
vol="${COMPOSE_PROJECT_NAME:-mediastack}_plex_config"
docker volume inspect "$vol" >/dev/null 2>&1 || { echo "volume $vol not found (set COMPOSE_PROJECT_NAME?)" >&2; exit 1; }
docker compose stop plex >/dev/null
docker run --rm -v "$vol":/src:ro -v "$(realpath "$out")":/out alpine \
  tar --exclude='./Library/Application Support/Plex Media Server/Cache' -czf /out/plex.tgz -C /src .
docker compose start plex >/dev/null

# your settings (contains secrets — keep the backup dir private)
cp .env "$out/env" 2>/dev/null || true
[ -d local ] && tar -czf "$out/local.tgz" local
cp config/stack/credentials.env "$out/" 2>/dev/null || true

ls -1dt "$dest"/mediastack-* | tail -n +$((keep + 1)) | xargs -r rm -rf
echo "backup written to $out"
