#!/usr/bin/env python3
"""
Roulette telnet server.

Listen on port 6666. On connect:
  1. Animate a spinning roulette wheel in the terminal (ANSI).
  2. Pick a random backend.
  3. Transparently bridge the telnet client <-> chosen backend port.

Backends:
  127.0.0.1:2323 - rickroll
  127.0.0.1:2324 - nyan-cat
  127.0.0.1:2325 - what-does-the-fox-say
  127.0.0.1:2326 - gangnam-style
  127.0.0.1:2327 - chocolate-rain
  127.0.0.1:2328 - baby-shark

Usage:
    python3 roulette_server.py
    telnet 127.0.0.1 6666
"""

import socket
import threading
import random
import time
import select

LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 6666

BACKENDS = [
    ("127.0.0.1", 2323, "rickroll"),
    ("127.0.0.1", 2324, "nyan-cat"),
    ("127.0.0.1", 2325, "what-does-the-fox-say"),
    ("127.0.0.1", 2326, "gangnam-style"),
    ("127.0.0.1", 2327, "chocolate-rain"),
    ("127.0.0.1", 2328, "baby-shark"),
]

CLS = "\x1b[2J\x1b[H"
HIDE = "\x1b[?25l"
SHOW = "\x1b[?25h"
RESET = "\x1b[0m"
BOLD = "\x1b[1m"
COLORS = ["\x1b[91m", "\x1b[92m", "\x1b[93m", "\x1b[94m", "\x1b[95m", "\x1b[96m"]


def send(conn, text):
    conn.sendall(text.replace("\n", "\r\n").encode("utf-8", "replace"))


def draw_wheel(conn, highlight, spinning=True):
    lines = [CLS, BOLD + "        \U0001F3B0  R O U L E T T E  \U0001F3B0" + RESET, ""]
    for i, (_, _, name) in enumerate(BACKENDS):
        color = COLORS[i % len(COLORS)]
        if i == highlight:
            row = f"{BOLD}{color}  >>> {name.upper():^22} <<<{RESET}"
        else:
            row = f"{color}      {name:^22}     {RESET}"
        lines.append(row)
    lines.append("")
    lines.append("        " + ("spinning..." if spinning else "LOCKED IN!"))
    send(conn, "\n".join(lines))


def spin(conn):
    n = len(BACKENDS)
    target = random.randrange(n)
    total_steps = n * random.randint(3, 5) + target
    delay = 0.04
    send(conn, HIDE)
    for step in range(total_steps + 1):
        draw_wheel(conn, step % n, spinning=True)
        time.sleep(delay)
        if step > total_steps - n:
            delay += 0.06
    draw_wheel(conn, target, spinning=False)
    send(conn, SHOW)
    time.sleep(0.8)
    return target


def bridge(client, backend):
    socks = [client, backend]
    try:
        while True:
            r, _, x = select.select(socks, [], socks, 60)
            if x:
                break
            if not r:
                continue
            for s in r:
                other = backend if s is client else client
                data = s.recv(4096)
                if not data:
                    return
                other.sendall(data)
    except OSError:
        pass


def handle(client, addr):
    try:
        send(client, CLS + "Connecting to the wheel of fortune...\n")
        time.sleep(0.4)
        idx = spin(client)
        host, port, name = BACKENDS[idx]
        send(client, f"\n\n>>> You landed on: {BOLD}{name}{RESET} ({host}:{port})\n")
        time.sleep(0.6)
        try:
            backend = socket.create_connection((host, port), timeout=5)
        except OSError as e:
            send(client, f"\nBackend {name} unavailable: {e}\n")
            return
        send(client, "\n" + "-" * 40 + "\n")
        bridge(client, backend)
    except OSError:
        pass
    finally:
        try:
            client.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        client.close()


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((LISTEN_HOST, LISTEN_PORT))
    srv.listen(16)
    print(f"Roulette server on {LISTEN_HOST}:{LISTEN_PORT} - telnet in to spin.")
    try:
        while True:
            client, addr = srv.accept()
            threading.Thread(target=handle, args=(client, addr), daemon=True).start()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        srv.close()


if __name__ == "__main__":
    main()
