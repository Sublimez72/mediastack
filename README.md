# mediastack

Plex + the *arr stack in one `docker compose up`. Everything is already wired together with
[TRaSH-guide](https://trash-guides.info) settings. You don't click through any setup wizards, and you don't copy API keys between apps.

| | |
|---|---|
| **Plex** | media server |
| **Seerr** | request movies & shows (friends get this link) |
| **Sonarr / Radarr** | find, grab, rename and import TV / movies |
| **Prowlarr + FlareSolverr** | indexers, synced to Sonarr/Radarr |
| **qBittorrent + gluetun** | downloads, only ever through your VPN |
| **Bazarr** | subtitles |
| **recyclarr** | keeps quality profiles in line with TRaSH, daily |
| **decluttarr** | clears stalled / failed / slow downloads |
| **Tautulli** | watch stats |
| **stack-init** | the glue: discovers every API key and configures every app from [`stack/stack.yml`](stack/stack.yml) |

## Quick start

You need Docker (Docker Desktop on Windows/macOS, or Docker Engine + compose plugin on Linux) and a VPN that
supports WireGuard ([supported providers](https://github.com/qdm12/gluetun-wiki/tree/main/setup/providers)).

```bash
git clone <this repo> mediastack && cd mediastack
cp .env.example .env        # fill in the 3 required lines
docker compose up -d
```

The 3 required lines:

- `VPN_SERVICE_PROVIDER` + `WIREGUARD_PRIVATE_KEY`, from your VPN account's WireGuard config.
- `PLEX_CLAIM`, from <https://plex.tv/claim>. It expires after 4 minutes, so grab it right before `up`.

The first start takes a few minutes. When it's done, `docker compose logs stack-init` ends with a list of URLs.
**Your login for every web UI is in `config/stack/credentials.env`.** Set `ADMIN_PASSWORD` in `.env` if you'd rather pick it yourself.

Open Seerr at <http://localhost:5055> and sign in with Plex. That's it.

## How it fits together

```
 ${MEDIA_ROOT}  ──►  /data   (one mount for everything → instant hardlink imports)
   ├── downloads/{radarr,tv-sonarr}   qBittorrent saves here, by category
   ├── movies/                        Radarr library  ─┐
   ├── tv/                            Sonarr library  ─┴─► Plex libraries
   └── .recycle/                      deleted files wait here 14 days
```

1. **`stack-prep`** runs first. It creates the folders, the shared admin login and qBittorrent's initial config.
2. The apps start and generate their own API keys.
3. **`stack-init`** reads those keys from each app's config. It then sets everything through each app's API:
   - **Sonarr/Radarr:** root folders, download client, media management, recycle bin, delay profile and Plex library updates.
   - **Prowlarr:** sync to Sonarr/Radarr, FlareSolverr and public indexers.
   - **qBittorrent:** categories and seeding limits.
   - **Bazarr:** Sonarr/Radarr connections, language profile and providers.
   - **Plex:** libraries.
   - **Seerr:** admin account, Plex and Sonarr/Radarr defaults, with no setup wizard.
   - **Tautulli:** connection to Plex.

   It also runs recyclarr and writes decluttarr's config.
4. Then it exits. It runs again on every `docker compose up` but only changes what drifted, so it's safe to re-run.

Torrents seed to ratio 2 or 14 days, then Sonarr/Radarr remove the download copy. The library file stays, because it's a hardlink.

## Customising

Don't edit the committed files. Put your overrides in **`local/`**, which is gitignored:

| want to change | do this |
|---|---|
| any setting in `stack/stack.yml` | create `local/stack.yml` with just the keys you want. Maps merge; lists replace. |
| quality profiles | copy `stack/recyclarr.yml` → `local/recyclarr.yml`, set `RECYCLARR_CONFIG=./local/recyclarr.yml` |
| add your own containers | `compose.override.yml` (auto-loaded; if you set `COMPOSE_FILE`, add it there too) |

Example `local/stack.yml`:

```yaml
sonarr:
  root_folders: [/data/tv, /data/anime]
bazarr:
  languages: [en, es]
seerr:
  radarr: { profile: Remux + WEB 2160p }   # default new movie requests to 4K
```

Preview what a change will do, then apply it:

```bash
docker compose run --rm stack-init apply --dry-run
docker compose up -d
```

Settings you change in an app's UI stay as they are, unless `stack.yml` manages that same setting.

## Remote access to Seerr

Pick one, or none. The tunnel only starts once Seerr is fully set up, so a half-configured Seerr is never on the internet.

- **Tailscale.** Free, no domain, opens no ports.
  - Only people you invite to your tailnet can reach Seerr, at `https://mediastack.<your-tailnet>.ts.net`.
  - Set `COMPOSE_PROFILES=tailscale` and `TS_AUTHKEY` (from the [Tailscale admin console](https://login.tailscale.com/admin/settings/keys)).
- **Cloudflare Tunnel.** A public URL on your own domain. The tunnel is free; the domain is not (Cloudflare's no-domain "quick tunnels" change URL on every restart).
  - Create a tunnel in Zero Trust → Networks → Tunnels and point its public hostname at `http://seerr:5055`.
  - Set `COMPOSE_PROFILES=cloudflare` and `CLOUDFLARE_TUNNEL_TOKEN`.
  - Optionally add an Access policy (email allowlist; free up to 50 users).

## Security defaults

- Every web UI requires the admin login. That includes requests from your LAN and from other containers; nothing is exempt for "local addresses".
- Web UIs listen on `127.0.0.1` only. Set `BIND_ADDR=0.0.0.0` to reach them from other devices. Plex (32400) is always reachable.
- qBittorrent shares gluetun's network. If the VPN is down, it has no internet at all.
- No container gets the Docker socket.
- Secrets live only in `.env` and `config/`, both gitignored. To block accidental commits: `pip install pre-commit && pre-commit install`, which runs gitleaks on every commit.

## Hardware transcoding (optional, needs Plex Pass)

Add an override to `COMPOSE_FILE` in `.env`:

- NVIDIA: `compose.gpu-nvidia.yml`. Needs the NVIDIA Container Toolkit; Docker Desktop on Windows includes it.
- Intel / AMD on Linux: `compose.gpu-intel.yml`.

Then enable *Use hardware acceleration* in Plex → Settings → Transcoder.

## Backups

Settings rebuild themselves from this repo. History doesn't: watch history, requests and Plex metadata. Back those up with:

```bash
scripts/backup.sh /path/to/backups        # Linux/macOS (cron it nightly)
```

On Windows, use `scripts\backup.ps1 -BackupDir D:\Backups` and schedule it with Task Scheduler.

Seerr, Tautulli and Plex stop for a few seconds during the copy, so their databases are consistent. The last 14 backups are kept. The backup includes `.env`, so keep the backup folder private.

## Troubleshooting

- **What did setup do / what failed?** `docker compose logs stack-init`. Fix the cause, then `docker compose up -d` to re-run it.
- **qBittorrent unreachable.** The VPN isn't up: check `docker compose logs gluetun`.
- **Seerr shows "unhealthy".** Setup is waiting for Plex. Check that `PLEX_CLAIM` was fresh, then `docker compose up -d`.
- **Plex streams through the relay at home.** Set `PLEX_ADVERTISE_URL=http://<your-LAN-IP>:32400`.
- **An indexer couldn't be added.** The site is down or blocked on your network. It's retried on every run; remove it from `local/stack.yml` to stop trying.
- **Test the whole thing from scratch:** `tests/cleanroom.sh`. It uses a fake VPN and no published ports, so it can run beside a live stack.
