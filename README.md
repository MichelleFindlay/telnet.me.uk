# Telnet.me.uk

Stream any video as coloured ASCII/ANSI art over **telnet** or **netcat** — and
optionally spin a **roulette wheel** that drops each viewer into one of several
streams at random.

You supply the video. `asciivid` renders it to a compact frame cache and serves
it over a plain TCP socket, so anyone can watch it in their terminal:

```
telnet your-host 2323
```

It ships with a small set of `systemd` utilities so you can run **many
independent streams at once**, each on its own port, managed by name — plus a
standalone **roulette telnet server** that bridges players to those streams at
random.

---

## Contents

- [Requirements](#requirements)
- [Quick start](#quick-start)
- [How it works](#how-it-works)
- [The CLI](#the-cli)
  - [`render` — make a `.dat`](#render--make-a-dat)
  - [`serve` — stream a `.dat`](#serve--stream-a-dat)
  - [`play` — render + serve in one go](#play--render--serve-in-one-go)
- [Running as a service (multiple streams)](#running-as-a-service-multiple-streams)
  - [One-time install](#one-time-install)
  - [Add a stream](#add-a-stream)
  - [List / remove streams](#list--remove-streams)
  - [Managing instances directly](#managing-instances-directly)
- [Roulette telnet server](#-roulette-telnet-server)
  - [Backends](#backends)
  - [Running it directly](#running-it-directly)
  - [Configuration](#configuration)
  - [Running as a systemd service](#running-as-a-systemd-service)
  - [Notes](#notes)
- [Ports and networking](#ports-and-networking)
- [Exposing it publicly](#exposing-it-publicly)
- [Troubleshooting](#troubleshooting)
- [Credits & licence](#credits--licence)

---

## Requirements

- **Python 3.8+** — for `serve` (no third-party packages). The roulette server
  needs only Python 3.7+, also standard library only.
- **ffmpeg** (and optionally `ffprobe`) on `PATH` — only for `render` / `play`.
  Serving a pre-rendered `.dat` needs Python alone.
- A client: `telnet` or `nc` (netcat). For the roulette wheel, an ANSI-capable
  client in a real terminal.

---

## Quick start

```bash
# 1. Render a video you have the rights to into a frame cache
python3 asciivid.py render input.mp4 --width 100 --fps 12 --out myclip.dat

# 2. Serve it
python3 asciivid.py serve myclip.dat --port 2323

# 3. Watch it (from anywhere that can reach the host)
telnet localhost 2323
```

Or do steps 1–2 in one command:

```bash
python3 asciivid.py play input.mp4 --width 100 --fps 12 --port 2323
```

Playback **loops by default**. Press `Ctrl-C` in the client to disconnect
cleanly — your terminal is restored to its original state.

---

## How it works

`asciivid` splits the job into two stages so serving is cheap and instant:

1. **Render** (`render`) uses ffmpeg to decode the video, scale it down to a
   terminal-sized grid, and convert every frame to an ANSI string. All frames,
   plus metadata (size, fps, colour mode), are pickled and zlib-compressed into
   a single **`.dat` file** — the *frame cache*.
2. **Serve** (`serve`) loads a `.dat` and streams its frames over TCP with
   correct frame timing. It needs no ffmpeg and starts instantly, which makes it
   ideal for a long-running service.

Each client connection is handled in its own forked process, so multiple people
can watch the same stream simultaneously.

---

## The CLI

`asciivid.py` has three subcommands. Run `python3 asciivid.py <cmd> -h` for the
full option list.

### `render` — make a `.dat`

Converts a video into a frame cache.

```bash
python3 asciivid.py render input.mp4 --out myclip.dat
```

| Option      | Default      | Description                                                        |
|-------------|--------------|--------------------------------------------------------------------|
| `--width`   | `100`        | Frame width in characters.                                         |
| `--height`  | `0` (auto)   | Frame height in rows. `0` derives it from the source aspect ratio. |
| `--fps`     | `12`         | Frames per second to sample and play back.                         |
| `--color`   | `ansi256`    | `ansi256`, `truecolor`, or `mono`.                                 |
| `--out`     | `frames.dat` | Output cache path.                                                 |

Notes on choosing values:

- **Width** is the biggest lever on both quality and file size. `100` suits a
  normal terminal; `160`–`200` looks sharper on a maximised window but makes a
  bigger `.dat`.
- **Height auto-derivation** accounts for terminal cells being roughly twice as
  tall as they are wide, so circles stay round. Override with `--height` only if
  you want to force a specific grid.
- **`--color truecolor`** looks best on modern terminals (24-bit) but produces a
  larger cache and more bytes on the wire. `ansi256` is a good default; `mono`
  is tiny and works everywhere.
- **`--fps`** higher than ~15 rarely helps for ASCII and inflates the cache.

Example — a crisp, full-colour render:

```bash
python3 asciivid.py render input.mp4 --width 160 --fps 15 --color truecolor --out hq.dat
```

The command prints the resolved grid size and final cache size, e.g.:

```
rendering input.mp4 -> 160x60 @ 15fps (truecolor)
wrote hq.dat: 900 frames, 2048 KiB compressed
```

### `serve` — stream a `.dat`

Serves a pre-rendered cache over TCP.

```bash
python3 asciivid.py serve myclip.dat --host 0.0.0.0 --port 2323
```

| Option      | Default   | Description                                   |
|-------------|-----------|-----------------------------------------------|
| `--host`    | `0.0.0.0` | Interface to bind. `0.0.0.0` = all interfaces.|
| `--port`    | `2323`    | TCP port to listen on.                        |
| `--no-loop` | *(off)*   | Play once and disconnect instead of looping.  |

Stop the server with `Ctrl-C`.

### `play` — render + serve in one go

Convenience command: renders to a temporary cache, serves it, and deletes the
cache on exit. Takes the union of `render` and `serve` options.

```bash
python3 asciivid.py play input.mp4 --width 100 --fps 12 --port 2323
```

Handy for a quick one-off; for anything long-running, prefer `render` once and
`serve` the resulting `.dat` (that's what the service does).

---

## Running as a service (multiple streams)

The repo includes a `systemd` **template unit** and three helper commands so you
can run any number of streams as managed, boot-persistent services — each with
its own name, port, and clip.

Files involved:

| File                 | Purpose                                             |
|----------------------|-----------------------------------------------------|
| `asciivid@.service`  | systemd **template** unit (one file, many instances)|
| `install-service.sh` | one-time setup: user, code, unit, helper commands   |
| `asciivid-add`       | create & start a new stream by name                 |
| `asciivid-ls`        | list all streams, their ports and state             |
| `asciivid-rm`        | stop & remove a stream                              |

### One-time install

Run the installer once. It creates an unprivileged `asciivid` user, copies
`asciivid.py` into `/opt/asciivid`, installs the template unit, and puts the
helper commands on your `PATH` (`/usr/local/bin`).

```bash
sudo ./install-service.sh
```

You do **not** name any streams here — instances are created on demand
afterwards.

### Add a stream

Each stream is created by name. **`asciivid-add` expects a rendered `.dat`, not a
raw video** — render first, then add:

```bash
# render the clip
python3 asciivid.py render never-gonna-give-you-up.mp4 --width 100 --fps 12 --out /tmp/rickroll.dat

# create + start a stream called "rickroll" on port 2323
sudo asciivid-add rickroll /tmp/rickroll.dat 2323
```

Syntax:

```
sudo asciivid-add NAME /path/to/frames.dat PORT [HOST]
```

- **NAME** — letters, digits, `-`, `_` only. Becomes the systemd instance
  `asciivid@NAME`; its description shows `telnet-NAME`.
- **PORT** — 1–65535. `asciivid-add` warns if another instance already uses it.
- **HOST** — optional bind address; defaults to `0.0.0.0`.

Each stream gets its own directory under `/opt/asciivid/instances/NAME/`
containing a copy of the cache (`frames.dat`) and an `env` file with its port.
The instance is enabled (starts on boot) and started immediately.

Add as many as you like, each on a distinct port:

```bash
sudo asciivid-add starwars /tmp/starwars.dat 2324
sudo asciivid-add badapple /tmp/badapple.dat 2325
```

### List / remove streams

```bash
asciivid-ls
```

```
NAME                 PORT    STATE    UNIT
----                 ----    -----    ----
telnet-rickroll      2323    active   asciivid@rickroll
telnet-starwars      2324    active   asciivid@starwars
```

Remove one (stops it, disables boot start, deletes its directory):

```bash
sudo asciivid-rm rickroll
```

### Managing instances directly

The helpers are thin wrappers around normal `systemctl`, so you can also drive
instances by hand:

```bash
sudo systemctl restart asciivid@rickroll     # after swapping its frames.dat
sudo systemctl stop asciivid@rickroll
sudo systemctl start asciivid@rickroll
journalctl -u asciivid@rickroll -f           # live logs for one stream
```

To change the clip on an existing stream, replace its cache and restart:

```bash
sudo install -m 0644 /tmp/newclip.dat /opt/asciivid/instances/rickroll/frames.dat
sudo chown asciivid:asciivid /opt/asciivid/instances/rickroll/frames.dat
sudo systemctl restart asciivid@rickroll
```

---

## 🎰 Roulette Telnet Server

A telnet server that spins a roulette wheel and drops you into one of six
backend services at random. Connect, watch the wheel decelerate and lock in,
then get bridged straight to whatever it landed on. When a backend finishes,
you're returned to the wheel to spin again.

It pairs naturally with the `asciivid` streams above: run a handful of clips as
services, point the roulette at their ports, and let viewers gamble on what
they get.

### Backends

The server proxies to six local ports:

| Port | Service                 |
|------|-------------------------|
| 2323 | rickroll                |
| 2324 | nyan-cat                |
| 2325 | what-does-the-fox-say   |
| 2326 | gangnam-style           |
| 2327 | chocolate-rain          |
| 2328 | baby-shark              |

These are expected to be listening locally and to stream their content over a
raw TCP/telnet connection. The roulette server itself only handles the wheel
and the proxying — bring your own backends (e.g. `asciivid` streams).

### Running it directly

```bash
python3 roulette_server.py
```

Then, from another terminal:

```bash
telnet 127.0.0.1 6666
```

The wheel spins, locks onto a random backend, and bridges you through.
Press **Enter** at the finish prompt to spin again, or **q** to quit.

### Configuration

Edit the constants at the top of `roulette_server.py`:

- `LISTEN_HOST` / `LISTEN_PORT` — where the roulette server listens (default `0.0.0.0:6666`)
- `BACKENDS` — the `(host, port, name)` list to spin between

If you set `LISTEN_PORT` below 1024, either run as root or grant the
capability (see the systemd note below).

### Running as a systemd service

A unit file (`roulette.service`) is included. It runs the server as a
dedicated unprivileged user with a hardened sandbox.

```bash
# Place the script and create a service user
sudo mkdir -p /opt/roulette
sudo cp roulette_server.py /opt/roulette/
sudo useradd --system --no-create-home --shell /usr/sbin/nologin roulette
sudo chown -R roulette:roulette /opt/roulette

# Install and enable the unit
sudo cp roulette.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now roulette.service

# Check status and follow logs
sudo systemctl status roulette.service
journalctl -u roulette.service -f
```

Adjust `ExecStart`, `User`, `Group`, and `ReadOnlyPaths` in the unit if you
use a different path or user. For a privileged port (< 1024), add
`AmbientCapabilities=CAP_NET_BIND_SERVICE` to the `[Service]` section.

### Notes

- The wheel animation needs an ANSI-capable client; a plain socket dump won't
  render the colours or cursor moves.
- If the chosen backend isn't listening, you'll see an "unavailable" message
  and be returned to the wheel rather than dropped.
- The server is threaded and handles multiple concurrent players, each with
  their own independent spin.

---

## Ports and networking

- Each stream listens on **one TCP port**. Pick a distinct port per stream.
- Ports **below 1024** (including the real telnet port `23`) require a
  privileged bind. The template unit is hardened with **no capabilities**, so it
  can't bind low ports as shipped. To use port 23, add these two lines to the
  `[Service]` section of `asciivid@.service`, replacing the empty capability
  lines, then `daemon-reload` and restart:

  ```ini
  AmbientCapabilities=CAP_NET_BIND_SERVICE
  CapabilityBoundingSet=CAP_NET_BIND_SERVICE
  ```

- Confirm what's listening:

  ```bash
  ss -ltnp | grep asciivid
  ```

---

## Exposing it publicly

By default the service binds `0.0.0.0` (all interfaces), but reaching it from
outside still depends on your network:

- **Local firewall** — open the port, e.g. `sudo ufw allow 2323/tcp`.
- **Home network** — forward the port on your router to the host's LAN IP;
  viewers connect to your public IP (`curl ifconfig.me` to find it).
- **Cloud VM** — open the port in the provider's security group as well as any
  host firewall.

> ⚠️ **This is an unauthenticated public TCP service.** It forks a process per
> connection with only light limits (`LimitNOFILE`, `TasksMax`), so a determined
> client could open many sockets. Fine for a fun demo; if you leave it up, put it
> behind a firewall allowlist, a reverse proxy with connection limits, or a
> private overlay network (e.g. a mesh VPN) rather than the open internet.

---

## Troubleshooting

**`Unit asciivid@NAME.service does not exist`**
The template unit isn't installed. Run `sudo ./install-service.sh`, or install
just the template:
```bash
sudo install -m 0644 asciivid@.service /etc/systemd/system/asciivid@.service
sudo systemctl daemon-reload
```

**`command not found` when running `asciivid-add`**
Either the installer hasn't run yet, or `sudo`'s restricted `PATH` excludes
`/usr/local/bin`. Use the full path: `sudo /usr/local/bin/asciivid-add …`.

**`Permission denied` running `./asciivid-add`**
The copy in the repo isn't executable, and it's meant to be run from
`/usr/local/bin` after install anyway. Run the installer, then call it by bare
name without `./`.

**The stream starts but is empty / errors on load**
`serve` and `asciivid-add` take a **`.dat`, not an `.mp4`**. Render the video
first with `asciivid.py render`.

**Terminal looks garbled after connecting with an old client**
The server negotiates telnet character mode and uses the alternate screen
buffer. Very old or non-standard clients may not honour this; `nc` always works.

**Client hangs on connect**
Check the port is actually listening (`ss -ltnp`) and not blocked by a firewall
between you and the host.

**Roulette lands on a backend but shows "unavailable"**
That backend port isn't listening. Start the corresponding `asciivid` stream (or
other service) on the port listed in `BACKENDS`.

---

## Credits & licence

- Streaming, telnet negotiation, the `.dat` format, the server, the roulette
  wheel, and the systemd utilities are original to this project.
- Rendering is delegated to **[ffmpeg](https://ffmpeg.org/)** (called as an
  external program; not bundled).
- Telnet character-mode negotiation follows **RFCs 854/855/857/858**. The
  ASCII luminance ramp and ANSI escape sequences are long-standing common
  techniques.

Licensed under the **GNU General Public License v3.0**. See the [`LICENSE`](LICENSE)
file for the full text.
