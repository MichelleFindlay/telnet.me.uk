#!/usr/bin/env bash
#
# One-time setup for the asciivid multi-instance service.
# Installs the code, a dedicated user, the systemd TEMPLATE unit, and the
# `asciivid-add` / `asciivid-ls` / `asciivid-rm` helper commands.
#
# Usage:
#   sudo ./install-service.sh
#
# After this, create as many instances as you like:
#   sudo asciivid-add rickroll ./rickroll.dat 2323
#   sudo asciivid-add starwars ./starwars.dat 2324

set -euo pipefail

PREFIX=/opt/asciivid
UNIT=/etc/systemd/system/asciivid@.service
SVC_USER=asciivid
BINDIR=/usr/local/bin

if [[ $EUID -ne 0 ]]; then
    echo "error: run with sudo/root" >&2
    exit 1
fi

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
for f in asciivid.py "asciivid@.service" asciivid-add asciivid-ls asciivid-rm; do
    if [[ ! -f "$SRC_DIR/$f" ]]; then
        echo "error: $f not found next to this script" >&2
        exit 1
    fi
done

echo ">> creating system user '$SVC_USER'"
if ! id "$SVC_USER" &>/dev/null; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "$SVC_USER"
fi

echo ">> installing code into $PREFIX"
mkdir -p "$PREFIX/instances"
install -m 0755 "$SRC_DIR/asciivid.py" "$PREFIX/asciivid.py"
chown -R "$SVC_USER:$SVC_USER" "$PREFIX"

echo ">> installing template unit $UNIT"
install -m 0644 "$SRC_DIR/asciivid@.service" "$UNIT"

echo ">> installing helper commands into $BINDIR"
install -m 0755 "$SRC_DIR/asciivid-add" "$BINDIR/asciivid-add"
install -m 0755 "$SRC_DIR/asciivid-ls"  "$BINDIR/asciivid-ls"
install -m 0755 "$SRC_DIR/asciivid-rm"  "$BINDIR/asciivid-rm"

systemctl daemon-reload

echo
echo "setup complete. now create instances, e.g.:"
echo "  sudo asciivid-add rickroll /path/to/rickroll.dat 2323"
echo "  sudo asciivid-add starwars /path/to/starwars.dat 2324"
echo
echo "list them:   asciivid-ls"
echo "remove one:  sudo asciivid-rm rickroll"
