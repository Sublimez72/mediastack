# mediastack

Plex, Jellyfin and/or Emby, plus the *arr stack in one `docker compose up`. Run one media server or all three side by side on the same library. Everything is already wired together with
[TRaSH-guide](https://trash-guides.info) settings. You don't click through any setup wizards, and you don't copy API keys between apps.

| | |
|---|---|
| **Plex / Jellyfin / Emby** | media servers: any one, two or all three, sharing one library |
| **Seerr** | request movies & shows (friends get this link) |
| **Sonarr / Radarr** | find, grab, rename and import TV / movies |
| **Prowlarr + FlareSolverr** | indexers, synced to Sonarr/Radarr |
| **qBittorrent + gluetun** | downloads, only ever through your VPN |
| **SABnzbd** *(optional)* | Usenet downloads, see [Usenet](#usenet-optional) |
| **Bazarr** | subtitles |
| **recyclarr** | keeps quality profiles in line with TRaSH, daily |
| **decluttarr** | clears stalled / failed / slow downloads |
| **Tautulli** | watch stats (Plex) |
| **stack-init** | the glue: discovers every API key and configures every app from [`stack/stack.yml`](stack/stack.yml) |

## Quick start

### What you need

- **Docker:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) on Windows/macOS, or Docker Engine + the compose plugin on Linux.
- **A VPN subscription with WireGuard**, for example ProtonVPN, Mullvad, AirVPN, Surfshark, Windscribe or IVPN ([full list](https://github.com/qdm12/gluetun-wiki/tree/main/setup/providers)).
- **For Plex: a Plex account**, ideally with [Plex Pass](https://www.plex.tv/plex-pass/), which unlocks hardware transcoding. A free account works too, but then Plex transcodes on the CPU only. Jellyfin needs no account and transcodes on the GPU for free. Emby needs [Emby Premiere](https://emby.media/premiere.html) for GPU transcoding.
- **A GPU (recommended):** an NVIDIA card (Windows or Linux), or Intel / AMD graphics (Linux only). See [Hardware transcoding](#hardware-transcoding) for the one-time driver setup, and do it before step 6.
- **Git**, to download this repo ([Git for Windows](https://git-scm.com/download/win); usually preinstalled on Linux/macOS).

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

### 3. Fill in your VPN details

Open `.env` in any text editor. Fill in the two VPN lines at the top. Leave `PLEX_CLAIM` empty for now: it comes in step 7.

When filled in, they look like this. The `x`s stand in for your own values; the lengths are real.

```ini
VPN_SERVICE_PROVIDER=protonvpn
WIREGUARD_PRIVATE_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx=
```

Rules for every line in `.env`:
- Use the format `NAME=value`.
- Don't put spaces around the `=`.
- Don't use quotes.

What goes in each line:

- **`VPN_SERVICE_PROVIDER`:** your VPN company, in lowercase. Examples: `protonvpn`, `mullvad`, `airvpn`, `surfshark`, `windscribe`, `ivpn`. Use the exact spelling from the [provider list](https://github.com/qdm12/gluetun-wiki/tree/main/setup/providers).
- **`WIREGUARD_PRIVATE_KEY`:** from a WireGuard config file you download from your VPN account. Create a new config just for this server; don't reuse one that's already connected somewhere else.
  - **ProtonVPN:** account.protonvpn.com → Downloads → WireGuard configuration. Platform: Router, NAT-PMP on if you want port forwarding.
  - **Mullvad:** mullvad.net → Account → WireGuard configuration.

  Open the downloaded `.conf` file in a text editor and copy the value after `PrivateKey = `. It's 44 characters and ends with `=`.

  Some providers also need lines from that same file (copy their values the same way):
  - **Mullvad, AirVPN, Surfshark, Windscribe, IVPN:** also add the `Address` value, e.g. `WIREGUARD_ADDRESSES=10.64.222.21/32`.
  - **AirVPN, Windscribe:** also add the `PresharedKey` value as `WIREGUARD_PRESHARED_KEY=...`.

**Optional: name your server.** Friends see this name in their Plex, Jellyfin or Emby apps. It defaults to `mediastack`. To pick your own, add a line like this (spaces are fine here, but no quotes). You can change it any time; it applies on the next `docker compose up -d`.

```ini
SERVER_NAME=Movie Night
```

(`PLEX_SERVER_NAME` from older versions still works.)

Everything else in `.env` is optional and commented out (`#`). You can leave it alone.

### 4. Choose your media servers

Plex is on unless you say otherwise. Add Jellyfin, Emby or both with one line in `.env`. They all show the same Movies and TV Shows from the same folders, so you can try one without giving up another.

| You want | Add to `.env` |
|---|---|
| Plex only | nothing |
| Plex + Jellyfin | `COMPOSE_PROFILES=jellyfin` |
| Plex + Emby | `COMPOSE_PROFILES=emby` |
| Plex + Jellyfin + Emby | `COMPOSE_PROFILES=jellyfin,emby` |
| No Plex | the same line, plus `compose.no-plex.yml` in `COMPOSE_FILE` (step 5) |

Already using `COMPOSE_PROFILES` for [Usenet](#usenet-optional) or [remote access](#remote-access-to-seerr)? Put them all on one line, e.g. `COMPOSE_PROFILES=jellyfin,usenet,tailscale`.

To run **without Plex**, also add `compose.no-plex.yml` to the `COMPOSE_FILE` line from step 5 (that also switches off Tautulli, which only works with Plex). Without a GPU line it looks like this; Windows uses `;` instead of `:`:

```ini
COMPOSE_FILE=compose.yml:compose.no-plex.yml
```

See [Media servers](#media-servers) for how they share the library and which one Seerr uses.

### 5. Turn on your GPU

Add one more line to `.env` for your graphics hardware. Pick the line that matches your GPU and operating system:

| GPU | Windows | Linux |
|---|---|---|
| NVIDIA | `COMPOSE_FILE=compose.yml;compose.gpu-nvidia.yml` | `COMPOSE_FILE=compose.yml:compose.gpu-nvidia.yml` |
| Intel / AMD | not supported by Docker Desktop, skip this step | `COMPOSE_FILE=compose.yml:compose.gpu-intel.yml` |

Windows uses `;` between the file names; Linux uses `:`. On macOS, skip this step: Docker can't pass a GPU through there.

The GPU line works for every media server you switched on. Running without Plex? Keep `compose.no-plex.yml` in the same line, e.g. `COMPOSE_FILE=compose.yml:compose.no-plex.yml:compose.gpu-nvidia.yml`.

### 6. Download everything

This downloads all the apps (a few GB) and takes about 5–10 minutes. If you use Plex, doing it before the Plex step matters: the claim code in step 7 expires after 4 minutes.

```bash
docker compose pull
```

```bash
docker compose build
```

### 7. Claim your Plex server and start

**No Plex?** Just start the stack with `docker compose up -d` and go to step 8.

With Plex, do these three things in one go, without a break:

1. Sign in at <https://plex.tv/claim> and copy the code that starts with `claim-`.
2. Paste it into `.env` after `PLEX_CLAIM=`, and save:
   ```ini
   PLEX_CLAIM=claim-xxxxxxxxxxxxxxxxxxxx
   ```
3. Start the stack:
   ```bash
   docker compose up -d
   ```

Plex uses the code within seconds of starting. Missed the 4 minutes? See [Troubleshooting](#troubleshooting).

Setup finishes in a few minutes. See what was set up:

```bash
docker compose logs stack-init
```

The log ends with a list of web addresses. After the first start, the claim code is no longer needed. You can leave it in `.env` or delete the line.

### 8. Log in

- **Your username and password for every web UI** (Sonarr, Radarr, qBittorrent…, and the Jellyfin/Emby admin) are in `config/stack/credentials.env`. Prefer your own password? Add `ADMIN_PASSWORD=yourpassword` to `.env` and run `docker compose up -d` again.
- **To request stuff:** open Seerr at <http://localhost:5055> and sign in with Plex, or with your Jellyfin/Emby login if Seerr is linked to one of those (see [Media servers](#media-servers)).
- **To watch:** your server shows up under the name from `SERVER_NAME` (default `mediastack`).
  - **Plex:** any Plex app or <https://app.plex.tv>.
  - **Jellyfin:** any Jellyfin app, or <http://localhost:8096>. In an app, enter your computer's address with port 8096, e.g. `http://192.168.1.50:8096`.
  - **Emby:** any Emby app, or <http://localhost:8097>. Apps need port 8097, e.g. `http://192.168.1.50:8097`.
- **Friends on Jellyfin or Emby** need their own user: create one in the server's Dashboard → Users. Plex friends are invited from Plex as usual.

### 9. Add indexers

Indexers are the sites Sonarr and Radarr search for downloads. **None come preinstalled**: you choose your own. You only add them in Prowlarr; it passes them on to Sonarr and Radarr automatically.

1. Open Prowlarr at <http://localhost:9696> and log in (same login as step 8).
2. Go to **Indexers** → **Add Indexer**.
3. Search for a site, click it, and click **Save**. Prowlarr tests the connection before saving.
   - **Public** sites need no account.
   - **Private** sites need an account there. Prowlarr asks for your API key, or your username and password, for that site.
4. Repeat for as many as you like. A handful of reliable ones is better than dozens of flaky ones.

Within a minute they appear in Sonarr and Radarr under Settings → Indexers. There's nothing to do there.

**Site behind Cloudflare** (the test fails with a Cloudflare or "challenge" error): open that indexer in Prowlarr, pick `flaresolverr` in the **Tags** field, and save. That sends its traffic through FlareSolverr, which is already set up for you.

**Optional: add them in a file instead.** Indexers added in Prowlarr live in its database, and setup never removes them. If you'd like a fresh install to re-add them automatically, list them in `local/stack.yml` instead. Use the exact name shown in Prowlarr's **Add Indexer** list, and only public sites:

```yaml
prowlarr:
  indexers:
    - { name: Internet Archive }
```

Add `flaresolverr: true` inside the braces for Cloudflare-protected sites. Then run `docker compose up -d`.

## How it fits together

```
 ${MEDIA_ROOT}  ──►  /data   (one mount for everything → instant hardlink imports)
   ├── downloads/{radarr,tv-sonarr}   qBittorrent saves here, by category
   ├── usenet/complete/{movies,tv}    SABnzbd saves here (only with Usenet on)
   ├── movies/                        Radarr library  ─┐
   ├── tv/                            Sonarr library  ─┴─► Plex / Jellyfin / Emby libraries
   └── .recycle/                      deleted files wait here 14 days
```

1. **`stack-prep`** runs first. It creates the folders, the shared admin login and qBittorrent's initial config.
2. The apps start and generate their own API keys.
3. **`stack-init`** reads those keys from each app's config. It then sets everything through each app's API:
   - **Sonarr/Radarr:** root folders, download client, media management, recycle bin, delay profile, and library updates for every media server that's on.
   - **Prowlarr:** sync to Sonarr/Radarr and FlareSolverr. Indexers are yours to add (Quick start step 9).
   - **qBittorrent:** categories and seeding limits.
   - **SABnzbd** (if Usenet is on): login, folders, categories, safety settings and your provider.
   - **Bazarr:** Sonarr/Radarr connections, language profile and providers.
   - **Plex:** libraries, server name, hardware transcoding.
   - **Jellyfin / Emby:** the first-run wizard (with the shared admin login), libraries, server name, and Jellyfin's hardware transcoding.
   - **Seerr:** admin account, its media server, and Sonarr/Radarr defaults, with no setup wizard.
   - **Tautulli:** connection to Plex.

   It also runs recyclarr and writes decluttarr's config.
4. Then it exits. It runs again on every `docker compose up` but only changes what drifted, so it's safe to re-run.

Torrents seed to ratio 2 or 14 days, then Sonarr/Radarr remove the download copy. The library file stays, because it's a hardlink.

## Updating

Get the latest version of this repo and of every app:

```bash
git pull
```

```bash
docker compose pull
```

```bash
docker compose build
```

```bash
docker compose up -d
```

Your settings, library and history are kept. stack-init runs again and only fixes anything that drifted.

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
  radarr: { profile: WEB 2160p }           # default new movie requests to 4K WEB
  sonarr: { profile: WEB-720p }            # default new TV requests to 720p
```

Preview what a change will do, then apply it:

```bash
docker compose run --rm stack-init apply --dry-run
docker compose up -d
```

Settings you change in an app's UI stay as they are, unless `stack.yml` manages that same setting.

## Media servers

Plex, Jellyfin and Emby can run in any combination (Quick start step 4). What to know when you run more than one:

- **One library, read by all.** Every server gets the same Movies and TV Shows folders. New downloads show up in every running server straight away, because Sonarr/Radarr tell each one to rescan.
- **Nothing is written into your media folders.** Jellyfin and Emby keep their metadata and artwork in their own config, so they don't leave `.nfo` files or posters next to your movies for the other servers (or Sonarr/Radarr) to trip over.
- **Watch history is per server.** Watching a film in Jellyfin doesn't mark it watched in Plex.
- **Seerr links to one server.** Seerr only supports one. At its first setup it picks Plex if Plex is on, otherwise Jellyfin, otherwise Emby. Friends sign into Seerr with an account on that server. To choose, put this in `local/stack.yml` before Seerr's first setup:
  ```yaml
  seerr:
    media_server: jellyfin     # plex, jellyfin or emby
  ```
  Requests still land in the shared folders, so every server gets them. To move an already set-up Seerr to a different server, stop it, delete `config/seerr`, and run `docker compose up -d` (this resets Seerr's request history).
- **Ports:** Plex 32400, Jellyfin 8096, Emby 8097 (Emby's usual 8096 is taken by Jellyfin, so it moves).
- **Stats:** Tautulli only works with Plex. Jellyfin and Emby show who's watching what in their own Dashboard.
- **Switching off a server** keeps its data in its Docker volume. Switch it back on and it picks up where it left off.

## Usenet (optional)

Usenet is a paid alternative to torrents: downloads are usually faster and complete, and nothing is uploaded. You need two things:

- **A Usenet provider** (the servers you download from), for example Newshosting, Eweka, Frugal Usenet or UsenetExpress. It's a monthly or yearly subscription.
- **At least one Usenet indexer** (the sites that list what's on those servers), for example NZBgeek, DrunkenSlug or NZBFinder. Most cost a few dollars a year.

Turn it on by adding these lines to `.env`, with your provider's details:

```ini
COMPOSE_PROFILES=usenet
USENET_HOST=news.yourprovider.com
USENET_USERNAME=your-username
USENET_PASSWORD=your-password
```

Optional: `USENET_PORT` (default `563`, SSL) and `USENET_CONNECTIONS` (default `8`; set it to what your plan allows). Already using `COMPOSE_PROFILES` for Jellyfin/Emby or remote access? List them all, separated by commas: `COMPOSE_PROFILES=jellyfin,usenet,tailscale`.

Then run `docker compose up -d`. stack-init sets up SABnzbd with your provider and adds it to Sonarr and Radarr as a second download client. Then:

1. Add your Usenet indexer in Prowlarr, the same way as in [step 9](#9-add-indexers). Prowlarr passes it on to Sonarr and Radarr.
2. SABnzbd is at <http://localhost:8085>, with the same login as every other app. You don't need to change anything there.

When a release exists on both, Sonarr and Radarr pick the Usenet one. To keep preferring torrents, set `sabnzbd: { prefer_usenet: false }` in `local/stack.yml`.

SABnzbd isn't routed through the VPN: its connection to your provider is SSL-encrypted, and unlike torrents, nobody else can see what you download. It aborts downloads that are password-protected or contain programs instead of video, so Sonarr/Radarr move on to another release.

To turn Usenet off again, remove `usenet` from `COMPOSE_PROFILES`, run `docker compose rm -sf sabnzbd` to stop it, then `docker compose up -d`. stack-init removes SABnzbd from Sonarr and Radarr.

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
- Web UIs listen on `127.0.0.1` only. Set `BIND_ADDR=0.0.0.0` to reach them from other devices. The media servers (Plex 32400, Jellyfin 8096, Emby 8097) are always reachable, so your TVs and phones can find them; each has its own login.
- qBittorrent shares gluetun's network. If the VPN is down, it has no internet at all.
- No container gets the Docker socket.
- Secrets live only in `.env` and `config/`, both gitignored. To block accidental commits: `pip install pre-commit && pre-commit install`, which runs gitleaks on every commit.

## Hardware transcoding

When a device can't play a file as-is (a phone on mobile data, a TV that doesn't support the format, a friend on slow internet), the media server converts it on the fly. On the CPU, a single 4K conversion can max out a weaker machine. A GPU's video hardware handles several at once with almost no load.

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

No permission setup is needed: the media server containers give themselves access to the device on start.

### In the stack

- Add the matching `COMPOSE_FILE` line to `.env` (Quick start step 5). It passes the GPU to every media server that's on; they can share it.
- **Plex:** *Use hardware acceleration when available* and *Use hardware-accelerated video encoding* are switched on by stack-init. Needs Plex Pass.
- **Jellyfin:** stack-init switches on hardware transcoding: NVENC for NVIDIA, VAAPI for Intel/AMD. Free. To fine-tune (for example on an older card without HEVC), override `jellyfin.hardware_acceleration` in `local/stack.yml`.
- **Emby:** needs Emby Premiere, then picks up the GPU on its own (Dashboard → Transcoding).

If you add the GPU line after the stack is already running, apply it with:

```bash
docker compose up -d
```

### Check it's working

1. Open any movie, then in the player pick a lower quality (for example *720p*). That forces a transcode.
2. Look at the stream on the server's dashboard:
   - **Plex:** Plex Web → Settings → Dashboard (top right, the activity icon). It should say **Transcode (hw)**.
   - **Jellyfin / Emby:** Dashboard → Active devices. The stream info should mention the GPU (for example *NVENC* or *VAAPI*).
3. If the GPU isn't being used:
   - **Plex without Plex Pass, or Emby without Premiere,** always uses the CPU.
   - **`COMPOSE_FILE` line missing or with the wrong separator** (`;` on Windows, `:` on Linux). To check, run `docker compose config` and look for a `devices:` section under your media server.
   - **NVIDIA on Linux:** the `nvidia-smi -L` check above fails, so the Container Toolkit isn't set up.

## Backups

Settings rebuild themselves from this repo. History doesn't: watch history, requests and your media servers' metadata. Back those up with:

```bash
scripts/backup.sh /path/to/backups        # Linux/macOS (cron it nightly)
```

On Windows, use `scripts\backup.ps1 -BackupDir D:\Backups` and schedule it with Task Scheduler.

Seerr, Tautulli and each media server stop for a few seconds during the copy, so their databases are consistent. The last 14 backups are kept. The backup includes `.env`, so keep the backup folder private.

## Troubleshooting

- **What did setup do / what failed?** `docker compose logs stack-init`. Fix the cause, then `docker compose up -d` to re-run it.
- **qBittorrent unreachable.** The VPN isn't up: check `docker compose logs gluetun`.
- **Usenet downloads fail straight away.** Check the provider details in `.env`, then open SABnzbd → Config → Servers and click **Test Server**. `docker compose logs sabnzbd` shows the error.
- **The Plex claim code expired** (Seerr shows "unhealthy", and the stack-init log says Plex is not claimed). Plex only tries the code once, when its container is first created. To retry:
  1. Get a fresh code at <https://plex.tv/claim> and replace the `PLEX_CLAIM=` value in `.env`.
  2. Straight away, recreate Plex so it tries again:
     ```bash
     docker compose up -d --force-recreate plex
     ```
  3. Finish the setup. Tautulli has to be stopped for setup to configure it:
     ```bash
     docker compose stop tautulli
     ```
     ```bash
     docker compose up -d
     ```
- **Plex streams through the relay at home.** Add your computer's LAN address to `.env`, e.g. `PLEX_ADVERTISE_URL=http://192.168.1.50:32400`. Find it with `ipconfig` (Windows) or `ip addr` (Linux): it's the `192.168.x.x` or `10.x.x.x` address.
- **An indexer from `local/stack.yml` couldn't be added.** The site is down or blocked on your network. It's retried on every run; remove it from `local/stack.yml` to stop trying.
- **Jellyfin or Emby setup was skipped with "can't sign in".** Their admin password was changed in their own settings. Set it back to the one in `config/stack/credentials.env` and run `docker compose up -d`.
- **Seerr waits for Plex but you'd rather use Jellyfin/Emby.** Set `seerr: { media_server: jellyfin }` (or `emby`) in `local/stack.yml` and run `docker compose up -d`.
- **Sonarr/Radarr find nothing.** Check that you've added indexers (Quick start step 9), and that Prowlarr → **Indexers** shows them without a red error. In Sonarr/Radarr, Settings → Indexers should list the same ones.
- **Test the whole thing from scratch:** `tests/cleanroom.sh` (add `MEDIA_SERVERS=plex,jellyfin,emby` in front to include the others). It uses a fake VPN and no published ports, so it can run beside a live stack.
