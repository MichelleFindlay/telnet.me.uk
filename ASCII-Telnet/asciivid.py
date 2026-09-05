#!/usr/bin/env python3
"""
asciivid.py - Stream any video as ASCII/ANSI art over telnet/nc.

You supply the video. This renders it to coloured ANSI frames and serves
them over a TCP socket, so `telnet HOST PORT` (or `nc HOST PORT`) plays it
in the terminal with correct frame timing.

Usage
-----
1. Pre-render a video to a frame cache:
       ./asciivid.py render input.mp4 --width 100 --fps 12 --out frames.dat

2. Serve it:
       ./asciivid.py serve frames.dat --port 2323

3. Watch from any machine:
       telnet YOUR_HOST 2323
       # or
       nc YOUR_HOST 2323

You can also do both at once (render to a temp cache, then serve):
       ./asciivid.py play input.mp4 --width 100 --fps 12 --port 2323

Notes
-----
* Requires ffmpeg on PATH for the render/play steps (serve needs only Python).
* --color ansi256 (default) or truecolor or mono.
* Ctrl-] then "quit" exits telnet; Ctrl-C exits nc.
"""

import argparse
import os
import pickle
import selectors
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import zlib

# Characters from dark -> light. Space is darkest.
RAMP = " .:-=+*#%@"

RESET = "\033[0m"
CLEAR = "\033[2J"
HOME = "\033[H"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"
ALT_SCREEN = "\033[?1049h"   # switch to alternate buffer
MAIN_SCREEN = "\033[?1049l"  # restore original buffer (undoes everything)

# Sequence sent to a client when its session ends, so its terminal is never
# left hidden-cursor / mid-colour / in the alt buffer.
CLEANUP = SHOW_CURSOR + RESET + MAIN_SCREEN

# Telnet negotiation (RFC 854/857/858). Put the client into character mode
# with the server suppressing go-ahead and handling echo, so the raw ANSI we
# stream doesn't wedge the client's line-buffered cooked mode.
IAC = 255
DONT, DO, WONT, WILL, SB, SE = 254, 253, 252, 251, 250, 240
OPT_ECHO, OPT_SGA = 1, 3
TELNET_INIT = bytes([
    IAC, WILL, OPT_ECHO,   # we'll echo (client stops local echo)
    IAC, WILL, OPT_SGA,    # suppress go-ahead -> character-at-a-time
    IAC, DONT, OPT_ECHO,   # client need not echo
])


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def check_ffmpeg():
    if shutil.which("ffmpeg") is None:
        sys.exit("error: ffmpeg not found on PATH (needed for render/play)")


def probe_size(path):
    """Return (w, h) of the source video via ffprobe, or None."""
    if shutil.which("ffprobe") is None:
        return None
    try:
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=s=x:p=0",
                path,
            ],
            text=True,
        ).strip()
        w, h = out.split("x")
        return int(w), int(h)
    except Exception:
        return None


def extract_frames(path, cols, rows, fps):
    """
    Yield raw RGB frames as bytes of length cols*rows*3, using ffmpeg.
    Scales to cols x rows and streams rawvideo on stdout.
    """
    cmd = [
        "ffmpeg", "-v", "error",
        "-i", path,
        "-vf", f"fps={fps},scale={cols}:{rows}:flags=bilinear",
        "-f", "rawvideo",
        "-pix_fmt", "rgb24",
        "-",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    frame_bytes = cols * rows * 3
    try:
        while True:
            buf = proc.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            yield buf
    finally:
        proc.stdout.close()
        proc.wait()


def rgb_to_ramp(r, g, b):
    lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
    return RAMP[min(len(RAMP) - 1, int(lum * (len(RAMP) - 1) + 0.5))]


def frame_to_ansi(buf, cols, rows, color):
    """Convert one raw RGB frame to an ANSI string (without cursor-home)."""
    out = []
    idx = 0
    last_code = None
    for _y in range(rows):
        line = []
        for _x in range(cols):
            r = buf[idx]; g = buf[idx + 1]; b = buf[idx + 2]
            idx += 3
            ch = rgb_to_ramp(r, g, b)
            if color == "mono":
                line.append(ch)
                continue
            if color == "truecolor":
                code = f"\033[38;2;{r};{g};{b}m"
            else:  # ansi256
                # 6x6x6 colour cube (codes 16-231)
                ri = r * 5 // 255
                gi = g * 5 // 255
                bi = b * 5 // 255
                code = f"\033[38;5;{16 + 36 * ri + 6 * gi + bi}m"
            if code != last_code:
                line.append(code)
                last_code = code
            line.append(ch)
        out.append("".join(line))
        last_code = None  # reset per line to avoid colour bleed on wrap
    body = "\r\n".join(out)
    if color != "mono":
        body += RESET
    return body


def do_render(args):
    check_ffmpeg()
    if not os.path.isfile(args.input):
        sys.exit(f"error: no such file: {args.input}")

    cols = args.width
    # derive rows from source aspect ratio; terminal cells are ~2x tall as wide
    size = probe_size(args.input)
    if size:
        sw, sh = size
        rows = max(1, int(cols * (sh / sw) * 0.5))
    else:
        rows = args.height or max(1, cols // 2)
    if args.height:
        rows = args.height

    print(f"rendering {args.input} -> {cols}x{rows} @ {args.fps}fps "
          f"({args.color})", file=sys.stderr)

    frames = []
    n = 0
    for buf in extract_frames(args.input, cols, rows, args.fps):
        frames.append(frame_to_ansi(buf, cols, rows, args.color))
        n += 1
        if n % 25 == 0:
            print(f"  {n} frames...", file=sys.stderr)

    if not frames:
        sys.exit("error: no frames produced (bad input or ffmpeg failure)")

    meta = {
        "cols": cols,
        "rows": rows,
        "fps": args.fps,
        "color": args.color,
        "frames": frames,
    }
    blob = zlib.compress(pickle.dumps(meta), 9)
    with open(args.out, "wb") as fh:
        fh.write(blob)
    print(f"wrote {args.out}: {n} frames, {len(blob)//1024} KiB compressed",
          file=sys.stderr)


# --------------------------------------------------------------------------- #
# Serving
# --------------------------------------------------------------------------- #
def load_cache(path):
    with open(path, "rb") as fh:
        return pickle.loads(zlib.decompress(fh.read()))


def _drain_input(conn, stop):
    """
    Read and discard everything the client sends, parsing the telnet protocol
    so that negotiation bytes are never mistaken for keystrokes. Runs in a
    background thread. Sets `stop` only on a genuine quit — the telnet
    interrupt-process command (IAC IP), or a real ^C / ^] / 'q' typed by the
    user outside any IAC sequence — or when the client disconnects.
    """
    QUIT_KEYS = {0x03, 0x1d, ord("q"), ord("Q")}  # ^C, ^], q, Q
    # tiny state machine over the telnet byte stream
    NORMAL, IAC_CMD, IAC_OPT, SUBNEG, SUBNEG_IAC = range(5)
    state = NORMAL
    try:
        while not stop.is_set():
            data = conn.recv(256)
            if not data:                 # client closed the connection
                stop.set()
                return
            for b in data:
                if state == NORMAL:
                    if b == IAC:
                        state = IAC_CMD
                    elif b in QUIT_KEYS:  # real keystroke -> quit
                        stop.set()
                        return
                    # any other byte is ignored (harmless input)
                elif state == IAC_CMD:
                    if b == IAC:          # escaped 0xFF data byte
                        state = NORMAL
                    elif b == SB:         # subnegotiation begins
                        state = SUBNEG
                    elif b == 244:        # IP = interrupt process (Ctrl-C)
                        stop.set()
                        return
                    elif b in (DO, DONT, WILL, WONT):
                        state = IAC_OPT   # one option byte follows
                    else:
                        state = NORMAL    # standalone command, no option
                elif state == IAC_OPT:
                    state = NORMAL        # consumed the option byte
                elif state == SUBNEG:
                    if b == IAC:
                        state = SUBNEG_IAC
                    # else: subnegotiation payload, ignored
                elif state == SUBNEG_IAC:
                    # IAC SE ends the subnegotiation; IAC IAC is escaped data
                    state = NORMAL if b == SE else SUBNEG
    except OSError:
        stop.set()


def stream_to_socket(conn, meta, loop):
    """Blocking playback loop for a single client. Returns on disconnect."""
    import threading

    fps = meta["fps"]
    delay = 1.0 / fps
    frames = meta["frames"]

    stop = threading.Event()
    reader = threading.Thread(target=_drain_input, args=(conn, stop),
                              daemon=True)
    reader.start()

    # Negotiate telnet character mode, then set up the screen.
    try:
        conn.sendall(TELNET_INIT)
        conn.sendall((ALT_SCREEN + HIDE_CURSOR + CLEAR).encode())
    except OSError:
        _cleanup(conn)
        return

    try:
        while not stop.is_set():
            for fr in frames:
                if stop.is_set():
                    break
                t0 = time.monotonic()
                conn.sendall((HOME + fr).encode("utf-8", "replace"))
                dt = time.monotonic() - t0
                sleep = delay - dt
                if sleep > 0:
                    # wait() returns early if the client quits mid-frame
                    if stop.wait(sleep):
                        break
            if not loop:
                break
            if stop.wait(0.2):   # tiny gap between loops, interruptible
                break
    except (BrokenPipeError, ConnectionResetError, OSError):
        pass
    finally:
        stop.set()
        _cleanup(conn)


def _cleanup(conn):
    """Restore the client's terminal. Safe to call more than once."""
    try:
        conn.sendall(CLEANUP.encode())
    except OSError:
        pass
    try:
        conn.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass


def do_serve(args):
    if not os.path.isfile(args.cache):
        sys.exit(f"error: no such cache file: {args.cache}")
    meta = load_cache(args.cache)
    print(f"loaded {args.cache}: {len(meta['frames'])} frames "
          f"{meta['cols']}x{meta['rows']} @ {meta['fps']}fps", file=sys.stderr)

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((args.host, args.port))
    srv.listen(16)
    print(f"serving on {args.host}:{args.port}  "
          f"(telnet/nc to watch; Ctrl-C to stop)", file=sys.stderr)

    try:
        while True:
            conn, addr = srv.accept()
            print(f"client {addr[0]}:{addr[1]} connected", file=sys.stderr)
            pid = os.fork() if hasattr(os, "fork") else None
            if pid == 0:
                # child
                srv.close()
                # Telnet sends option negotiation; drain anything it sends,
                # and put its terminal in a sane state via IAC WILL ECHO etc.
                # We simply ignore inbound bytes.
                conn.setblocking(True)
                stream_to_socket(conn, meta, args.loop)
                conn.close()
                os._exit(0)
            else:
                conn.close()  # parent doesn't need it
    except KeyboardInterrupt:
        print("\nshutting down", file=sys.stderr)
    finally:
        srv.close()


def do_play(args):
    """render to a temp cache, then serve."""
    tmp = tempfile.NamedTemporaryFile(suffix=".dat", delete=False)
    tmp.close()
    r = argparse.Namespace(
        input=args.input, width=args.width, height=args.height,
        fps=args.fps, color=args.color, out=tmp.name,
    )
    do_render(r)
    s = argparse.Namespace(
        cache=tmp.name, host=args.host, port=args.port, loop=args.loop,
    )
    try:
        do_serve(s)
    finally:
        os.unlink(tmp.name)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main():
    p = argparse.ArgumentParser(description="Stream video as ASCII over telnet.")
    sub = p.add_subparsers(dest="cmd", required=True)

    common_render = dict()

    pr = sub.add_parser("render", help="render a video to a frame cache")
    pr.add_argument("input")
    pr.add_argument("--width", type=int, default=100)
    pr.add_argument("--height", type=int, default=0,
                    help="rows (0 = auto from aspect ratio)")
    pr.add_argument("--fps", type=int, default=12)
    pr.add_argument("--color", choices=["ansi256", "truecolor", "mono"],
                    default="ansi256")
    pr.add_argument("--out", default="frames.dat")
    pr.set_defaults(func=do_render)

    ps = sub.add_parser("serve", help="serve a frame cache over TCP")
    ps.add_argument("cache")
    ps.add_argument("--host", default="0.0.0.0")
    ps.add_argument("--port", type=int, default=2323)
    ps.add_argument("--no-loop", dest="loop", action="store_false",
                    help="play once instead of looping forever")
    ps.set_defaults(func=do_serve, loop=True)

    pp = sub.add_parser("play", help="render + serve in one step")
    pp.add_argument("input")
    pp.add_argument("--width", type=int, default=100)
    pp.add_argument("--height", type=int, default=0)
    pp.add_argument("--fps", type=int, default=12)
    pp.add_argument("--color", choices=["ansi256", "truecolor", "mono"],
                    default="ansi256")
    pp.add_argument("--host", default="0.0.0.0")
    pp.add_argument("--port", type=int, default=2323)
    pp.add_argument("--no-loop", dest="loop", action="store_false",
                    help="play once instead of looping forever")
    pp.set_defaults(func=do_play, loop=True)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
