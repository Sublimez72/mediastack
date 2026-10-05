#!/usr/bin/env bash
# Spin the whole stack up from nothing in a scratch dir and check it wires itself.
#   tests/cleanroom.sh [workdir]      (cleanup: docker compose -p mstest down -v)
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
work=${1:-$repo/.cleanroom}
rm -rf "$work"; mkdir -p "$work"
cp -r "$repo/compose.yml" "$repo/stack" "$repo/stack-init" "$repo/tests" "$work/"
cat > "$work/.env" <<ENV
VPN_SERVICE_PROVIDER=test
WIREGUARD_PRIVATE_KEY=test
COMPOSE_PATH_SEPARATOR=:
COMPOSE_FILE=compose.yml:tests/compose.test.yml
ENV
cd "$work"
docker compose -p mstest up -d --build || true
docker compose -p mstest logs --no-log-prefix stack-init | tail -80
echo "--- second run (must be a no-op)"
docker compose -p mstest run --rm stack-init apply --dry-run | tail -25
