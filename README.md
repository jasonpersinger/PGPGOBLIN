<p align="center">
  <img src="pgpgoblin_icon.png" alt="PGPGOBLIN 8-Bit Logo" width="128" height="128" />
</p>

<h1 align="center">PGPGOBLIN</h1>

<p align="center">
  <strong>A zero-friction, 8-bit inspired Linux PGP scratchpad for encrypting, decrypting, and signing text via native GnuPG.</strong>
</p>

---

## Features

- **Zero Key Import Friction (`~/.gnupg`):** Automatically discovers encryption-capable public keys and your personal secret keys directly from your system GnuPG keyring.
- **Ephemeral "Paste Public Key" Mode:** Paste any raw `-----BEGIN PGP PUBLIC KEY BLOCK-----` to encrypt a one-off message in an isolated temporary keyring without cluttering `~/.gnupg` (or check a box to import & save it permanently).
- **Multi-Recipient & Self-Encryption:** Encrypt to a single recipient via the searchable dropdown, select multiple saved keys from a checklist, or include your own key (`Also encrypt to My Key`).
- **One-Click Public Key Export:** Click **📤 Export My Public Key** to immediately place your `-----BEGIN PGP PUBLIC KEY BLOCK-----` into the scratchpad and copy it to your clipboard.
- **Clear-Sign & Signature Verification:** Create `-----BEGIN PGP SIGNED MESSAGE-----` blocks with **✍ Clear-Sign** and verify signatures with **✓ Verify Sig** (including automatic verification of signed-and-encrypted messages).
- **Symmetric AES-256 Passphrase Encryption:** Click **🔑 Symmetric** to encrypt notes with a passphrase instead of a public key.
- **Native `gpg-agent` / `pinentry` Security:** PGPGOBLIN never captures or touches your passphrases. All private key and symmetric passphrase operations are delegated strictly to your system `gpg` and `pinentry`.
- **Drag-and-Drop File Support:** Drop `.asc`, `.gpg`, `.pgp`, `.pub`, or `.txt` files directly onto the scratchpad window.

---

## Installation

### Arch Linux (Native Package / `makepkg`)

```bash
sudo pacman -S --needed gnupg pinentry python python-gnupg python-pyqt6
git clone https://github.com/jasonpersinger/PGPGOBLIN.git
cd PGPGOBLIN
makepkg -si
```

### Universal Linux User Install (No Root Required)

1. Install system dependencies:
   - **Arch:** `sudo pacman -S gnupg pinentry python python-gnupg python-pyqt6`
   - **Debian / Ubuntu / Mint:** `sudo apt install gnupg pinentry-qt python3 python3-gnupg python3-pyqt6`
   - **Fedora:** `sudo dnf install gnupg2 pinentry python3 python3-gnupg python3-pyqt6`
2. Run the installer script:
   ```bash
   ./install.sh
   ```
   *(To uninstall later, run `./install.sh --uninstall`.)*

---

## Keyboard Shortcuts

| Shortcut | Action |
| :--- | :--- |
| `Ctrl+E` | **Encrypt** scratchpad to selected recipient(s) |
| `Ctrl+Shift+E` | **Symmetric** encrypt (AES-256 passphrase) |
| `Ctrl+D` | **Decrypt** PGP block in scratchpad |
| `Ctrl+S` | **Clear-Sign** plaintext with selected `My Key` |
| `Ctrl+Shift+V` | **Verify** PGP signature in scratchpad |
| `Ctrl+Shift+C` | **Copy** scratchpad content to clipboard |
| `Ctrl+L` | **Clear** scratchpad editor |
| `F5` | **Reload** GnuPG keyring from `~/.gnupg` |

---

## License

Released under the [MIT License](LICENSE).
