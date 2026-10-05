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

### What you need

- **Docker:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) on Windows/macOS, or Docker Engine + the compose plugin on Linux.
- **A VPN subscription with WireGuard**, for example ProtonVPN, Mullvad, AirVPN, Surfshark, Windscribe or IVPN ([full list](https://github.com/qdm12/gluetun-wiki/tree/main/setup/providers)).
- **A Plex account with [Plex Pass](https://www.plex.tv/plex-pass/).** Plex Pass is what unlocks hardware transcoding. A free account works too, but then Plex transcodes on the CPU only.
- **A GPU Plex can use:** an NVIDIA card (Windows or Linux), or Intel / AMD graphics (Linux only). See [Hardware transcoding](#hardware-transcoding) for the one-time driver setup, and do it before step 5.
- **Access to this repo.** It's private, so accept the GitHub invite first.

### 1. Download the stack

```bash
git clone https://github.com/Sublimez72/mediastack.git
cd mediastack
```

### 2. Create your `.env` file

Copy the example file. On Linux/macOS:

```bash
cp .env.example .env
```

On Windows (PowerShell):

```powershell
Copy-Item .env.example .env
```

### 3. Fill in the 3 required lines

Open `.env` in any text editor. The top of the file has the 3 lines you must fill in. When filled in, they look like this. The `x`s stand in for your own values; the lengths are real.

```ini
VPN_SERVICE_PROVIDER=protonvpn
WIREGUARD_PRIVATE_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx=
PLEX_CLAIM=claim-xxxxxxxxxxxxxxxxxxxx
```

Rules for every line in `.env`:
- Use the format `NAME=value`.
- Don't put spaces around the `=`.
- Don't use quotes.

What goes in each line:

- **`VPN_SERVICE_PROVIDER`:** your VPN company, in lowercase. Examples: `protonvpn`, `mullvad`, `airvpn`, `surfshark`, `windscribe`, `ivpn`. Use the exact spelling from the [provider list](https://github.com/qdm12/gluetun-wiki/tree/main/setup/providers).
- **`WIREGUARD_PRIVATE_KEY`:** from a WireGuard config file you download from your VPN account.
  - **ProtonVPN:** account.protonvpn.com → Downloads → WireGuard configuration. Platform: Router, NAT-PMP on if you want port forwarding.
  - **Mullvad:** mullvad.net → Account → WireGuard configuration.

  Open the downloaded `.conf` file in a text editor and copy the value after `PrivateKey = `. It's 44 characters and ends with `=`.

  Some providers also need lines from that same file (copy their values the same way):
  - **Mullvad, AirVPN, Surfshark, Windscribe, IVPN:** also add the `Address` value, e.g. `WIREGUARD_ADDRESSES=10.64.222.21/32`.
  - **AirVPN, Windscribe:** also add the `PresharedKey` value as `WIREGUARD_PRESHARED_KEY=...`.
- **`PLEX_CLAIM`:** sign in at <https://plex.tv/claim> and copy the code that starts with `claim-`.
  - **It expires after 4 minutes, so do this last**, right before step 4.
  - It's only needed the first time, while your new Plex server links to your account.

Everything else in `.env` is optional and commented out (`#`). You can leave it alone.

### 4. Turn on your GPU

Add one more line to `.env` for your graphics hardware. Pick the line that matches your GPU and operating system:

| GPU | Windows | Linux |
|---|---|---|
| NVIDIA | `COMPOSE_FILE=compose.yml;compose.gpu-nvidia.yml` | `COMPOSE_FILE=compose.yml:compose.gpu-nvidia.yml` |
| Intel / AMD | not supported by Docker Desktop, skip this step | `COMPOSE_FILE=compose.yml:compose.gpu-intel.yml` |

Windows uses `;` between the file names; Linux uses `:`. On macOS, skip this step: Docker can't pass a GPU through there.

### 5. Start it

```bash
docker compose up -d
```

The first start downloads everything and takes about 5–10 minutes. When the command finishes, see what was set up:

```bash
docker compose logs stack-init
```

The log ends with a list of web addresses.

### 6. Log in

- **Your username and password for every web UI** (Sonarr, Radarr, qBittorrent…) are in `config/stack/credentials.env`. Prefer your own password? Add `ADMIN_PASSWORD=yourpassword` to `.env` and run `docker compose up -d` again.
- **To request stuff:** open Seerr at <http://localhost:5055> and sign in with Plex.
- **To watch:** use any Plex app or <https://app.plex.tv>.

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
  - Only people you invite to your tailnet can reach Seerr. The address appears in the Tailscale admin console under Machines, e.g. `https://mediastack.tail1a2b3c.ts.net`.
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

## Hardware transcoding

When a device can't play a file as-is (a phone on mobile data, a TV that doesn't support the format, a friend on slow internet), Plex converts it on the fly. On the CPU, a single 4K conversion can max out a weaker machine. A GPU's video hardware handles several at once with almost no load.

### One-time setup on your computer

Do this before your first `docker compose up -d`.

**NVIDIA on Windows**
1. Install the latest [NVIDIA driver](https://www.nvidia.com/Download/index.aspx) (the normal GeForce / Studio driver).
2. In Docker Desktop → Settings → General, leave *Use the WSL 2 based engine* ticked (the default).

Docker Desktop has NVIDIA support built in, so there's nothing else to install.

**NVIDIA on Linux**
1. Install the NVIDIA driver from your distro (for example `sudo ubuntu-drivers install` on Ubuntu), then reboot.
2. Install the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html), then connect it to Docker:
   ```bash
   sudo nvidia-ctk runtime configure --runtime=docker
   ```
   ```bash
   sudo systemctl restart docker
   ```
3. Check that Docker can see the card. It should print your GPU's name:
   ```bash
   docker run --rm --gpus all ubuntu nvidia-smi -L
   ```

**Intel / AMD on Linux**
1. Check that the GPU device exists. It should list `renderD128`:
   ```bash
   ls /dev/dri
   ```
   If it doesn't, install your distro's Intel or AMD graphics drivers (on Ubuntu, `intel-media-va-driver-non-free` for Intel), then reboot.

No permission setup is needed: the Plex container gives itself access to the device on start.

### In the stack

- Add the matching `COMPOSE_FILE` line to `.env` (Quick start step 4).
- Plex's *Use hardware acceleration when available* and *Use hardware-accelerated video encoding* are switched on by stack-init. You don't need to touch Plex's settings.

If you add the GPU line after the stack is already running, apply it with:

```bash
docker compose up -d
```

### Check it's working

1. Open any movie in Plex, then in the player pick a lower quality (for example *720p*). That forces a transcode.
2. In Plex Web, open Settings → Dashboard (top right, the activity icon).
3. The stream should say **Transcode (hw)**. If it says *Transcode* without *(hw)*, the GPU isn't being used:
   - **No Plex Pass on the account that owns the server.** Without it, Plex always uses the CPU.
   - **`COMPOSE_FILE` line missing or with the wrong separator** (`;` on Windows, `:` on Linux). To check, run `docker compose config` and look for a `devices:` section under `plex:`.
   - **NVIDIA on Linux:** the `nvidia-smi -L` check above fails, so the Container Toolkit isn't set up.

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
- **Plex streams through the relay at home.** Add your computer's LAN address to `.env`, e.g. `PLEX_ADVERTISE_URL=http://192.168.1.50:32400`. Find it with `ipconfig` (Windows) or `ip addr` (Linux): it's the `192.168.x.x` or `10.x.x.x` address.
- **An indexer couldn't be added.** The site is down or blocked on your network. It's retried on every run; remove it from `local/stack.yml` to stop trying.
- **Test the whole thing from scratch:** `tests/cleanroom.sh`. It uses a fake VPN and no published ports, so it can run beside a live stack.
