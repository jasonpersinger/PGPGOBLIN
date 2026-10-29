#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${1:-}" == "--uninstall" ]]; then
    echo "Uninstalling PGPGOBLIN from ~/.local..."
    rm -f "$HOME/.local/bin/pgpgoblin"
    rm -f "$HOME/.local/share/applications/pgpgoblin.desktop"
    rm -f "$HOME/.local/share/icons/hicolor/512x512/apps/pgpgoblin.png"
    rm -f "$HOME/.local/share/icons/hicolor/scalable/apps/pgpgoblin.svg"
    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
    echo "✓ PGPGOBLIN uninstalled."
    exit 0
fi

echo "Installing PGPGOBLIN to ~/.local..."
if [[ -f "$SCRIPT_DIR/pgpgoblin.py" && -f "$SCRIPT_DIR/pgpgoblin_icon.png" ]]; then
    SRC_DIR="$SCRIPT_DIR"
else
    TMP_DIR="$(mktemp -d)"
    trap 'rm -rf "$TMP_DIR"' EXIT
    echo "Downloading PGPGOBLIN from GitHub..."
    curl -fsSL "https://github.com/jasonpersinger/PGPGOBLIN/archive/refs/heads/main.tar.gz" | tar -xz -C "$TMP_DIR"
    SRC_DIR="$TMP_DIR/PGPGOBLIN-main"
fi

install -Dm755 "$SRC_DIR/pgpgoblin.py" "$HOME/.local/bin/pgpgoblin"
install -Dm644 "$SRC_DIR/pgpgoblin_icon.png" "$HOME/.local/share/icons/hicolor/512x512/apps/pgpgoblin.png"
install -Dm644 "$SRC_DIR/pgpgoblin.svg" "$HOME/.local/share/icons/hicolor/scalable/apps/pgpgoblin.svg"

mkdir -p "$HOME/.local/share/applications"
sed "s|^Exec=pgpgoblin$|Exec=$HOME/.local/bin/pgpgoblin|" "$SRC_DIR/pgpgoblin.desktop" \
    > "$HOME/.local/share/applications/pgpgoblin.desktop"
chmod 644 "$HOME/.local/share/applications/pgpgoblin.desktop"

update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

echo "✓ PGPGOBLIN installed! Launch it from your desktop app menu or run: ~/.local/bin/pgpgoblin"
