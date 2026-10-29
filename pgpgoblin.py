#!/usr/bin/env python3
"""
PGPGOBLIN - A clean, self-contained Linux PGP scratchpad application.
Interfaces directly with the native system GnuPG keyring (~/.gnupg) and gpg-agent,
supporting saved keyring selection, raw public key pasting, clear-signing & signature
verification, one-click public key export, symmetric passphrase encryption, and
drag-and-drop file loading.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import gnupg

try:
    from PyQt6.QtCore import Qt, QUrl
    from PyQt6.QtGui import (
        QAction,
        QDragEnterEvent,
        QDropEvent,
        QFont,
        QGuiApplication,
        QIcon,
        QKeySequence,
    )
    from PyQt6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QDialog,
        QFileDialog,
        QFrame,
        QHBoxLayout,
        QLabel,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMessageBox,
        QPlainTextEdit,
        QPushButton,
        QStatusBar,
        QVBoxLayout,
        QWidget,
    )

    IS_PYQT6 = True
except ImportError:
    from PyQt5.QtCore import Qt, QUrl
    from PyQt5.QtGui import (
        QDragEnterEvent,
        QDropEvent,
        QFont,
        QGuiApplication,
        QIcon,
        QKeySequence,
    )
    from PyQt5.QtWidgets import (
        QAction,
        QApplication,
        QCheckBox,
        QComboBox,
        QDialog,
        QFileDialog,
        QFrame,
        QHBoxLayout,
        QLabel,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMessageBox,
        QPlainTextEdit,
        QPushButton,
        QStatusBar,
        QVBoxLayout,
        QWidget,
    )

    IS_PYQT6 = False


def get_gnupg_home() -> str:
    """Resolve the active GnuPG home directory (respecting $GNUPGHOME or ~/.gnupg)."""
    env_home = os.environ.get("GNUPGHOME")
    if env_home:
        return str(Path(env_home).expanduser().resolve())
    return str(Path.home() / ".gnupg")


def init_gpg_instance(gnupg_home: str) -> gnupg.GPG:
    """Initialize a python-gnupg instance pointing to the specified directory."""
    try:
        return gnupg.GPG(gnupghome=gnupg_home, use_agent=True)
    except TypeError:
        return gnupg.GPG(gnupghome=gnupg_home)


def format_key_label(key: dict[str, Any]) -> str:
    """Format a GnuPG key dictionary as a readable label."""
    fingerprint = key.get("fingerprint", "")
    keyid = key.get("keyid", fingerprint[-16:])
    short_id = keyid[-8:] if len(keyid) >= 8 else keyid
    uids = key.get("uids") or ["<No User ID>"]
    return f"{uids[0]}  [{short_id}]"


def is_usable_key(key: dict[str, Any], require_encrypt: bool = False) -> bool:
    """Return True if the key is not revoked/expired/disabled, and optionally can encrypt."""
    cap = key.get("cap", "")
    if key.get("trust") in ("r", "e") or "D" in cap:
        return False
    if require_encrypt and "e" not in cap and "E" not in cap:
        return False
    return True


def resolve_app_icon() -> QIcon:
    """Find the PGPGOBLIN custom icon from local or system paths."""
    base_dir = Path(__file__).resolve().parent
    for candidate in (
        base_dir / "pgpgoblin_icon.png",
        base_dir / "pgpgoblin.svg",
        Path.home() / ".local/share/icons/hicolor/512x512/apps/pgpgoblin.png",
        Path.home() / ".local/share/icons/hicolor/scalable/apps/pgpgoblin.svg",
        Path("/usr/share/icons/hicolor/512x512/apps/pgpgoblin.png"),
        Path("/usr/share/icons/hicolor/scalable/apps/pgpgoblin.svg"),
    ):
        if candidate.is_file():
            return QIcon(str(candidate))
    return QIcon.fromTheme("pgpgoblin")


class PastePublicKeyDialog(QDialog):
    """Modal dialog for pasting an ASCII-armored PGP public key block."""

    def __init__(self, parent: QWidget | None = None, initial_key: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("PGPGOBLIN — Paste Public Key")
        self.resize(650, 450)

        self.pasted_armored_key: str = initial_key
        self.save_to_keyring: bool = False
        self.detected_summary: str = ""
        self.detected_fingerprints: list[str] = []

        self._setup_ui(initial_key)

    def _setup_ui(self, initial_key: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        info_label = QLabel(
            "Paste an ASCII-armored PGP Public Key block below. You can encrypt to it "
            "ephemerally (zero trace in ~/.gnupg), or check the box to import it permanently."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        self.key_editor = QPlainTextEdit()
        self.key_editor.setPlaceholderText(
            "-----BEGIN PGP PUBLIC KEY BLOCK-----\n\n"
            "mQINBF...\n"
            "-----END PGP PUBLIC KEY BLOCK-----"
        )
        mono_font = QFont("Monospace")
        style_hint = QFont.StyleHint.Monospace if IS_PYQT6 else QFont.Monospace
        mono_font.setStyleHint(style_hint)
        mono_font.setPointSize(10)
        self.key_editor.setFont(mono_font)
        if initial_key:
            self.key_editor.setPlainText(initial_key)
        layout.addWidget(self.key_editor, stretch=1)

        self.save_cb = QCheckBox("Also import & save this key into my system keyring (~/.gnupg)")
        self.save_cb.setChecked(False)
        layout.addWidget(self.save_cb)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        paste_clip_btn = QPushButton("📋 Paste from Clipboard")
        paste_clip_btn.clicked.connect(self._paste_from_clipboard)
        btn_layout.addWidget(paste_clip_btn)

        btn_layout.addStretch(1)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        use_btn = QPushButton("✓ Use Public Key")
        use_btn.setObjectName("primaryActionBtn")
        use_btn.clicked.connect(self._validate_and_accept)
        btn_layout.addWidget(use_btn)

        layout.addLayout(btn_layout)

    def _paste_from_clipboard(self) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None and clipboard.text():
            self.key_editor.setPlainText(clipboard.text().strip())

    def _validate_and_accept(self) -> None:
        raw_block = self.key_editor.toPlainText().strip()
        if "-----BEGIN PGP PUBLIC KEY BLOCK-----" not in raw_block:
            QMessageBox.warning(
                self,
                "Invalid Public Key",
                "The pasted text does not contain a '-----BEGIN PGP PUBLIC KEY BLOCK-----' header.",
            )
            return

        tmp_dir = tempfile.mkdtemp(prefix="pgpgoblin_validate_")
        try:
            temp_gpg = init_gpg_instance(tmp_dir)
            import_result = temp_gpg.import_keys(raw_block)
            fps = getattr(import_result, "fingerprints", []) or []
            if not fps:
                QMessageBox.warning(
                    self,
                    "Key Parse Failed",
                    "GnuPG could not parse any valid public keys from the pasted block.",
                )
                return

            imported_keys = temp_gpg.list_keys(False)
            labels = [format_key_label(k) for k in imported_keys]
            self.detected_summary = ", ".join(labels) if labels else fps[0][-8:]
            self.detected_fingerprints = list(fps)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        self.pasted_armored_key = raw_block
        self.save_to_keyring = self.save_cb.isChecked()
        self.accept()


class MultiRecipientDialog(QDialog):
    """Modal dialog for selecting multiple saved keys from ~/.gnupg."""

    def __init__(
        self,
        public_keys: list[dict[str, Any]],
        selected_fps: list[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("PGPGOBLIN — Select Saved Keys")
        self.resize(580, 420)
        self.selected_fingerprints: list[str] = list(selected_fps)
        self._setup_ui(public_keys, selected_fps)

    def _setup_ui(
        self, public_keys: list[dict[str, Any]], selected_fps: list[str]
    ) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        header = QLabel(
            "Check one or more saved encryption-capable public keys from your keyring:"
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        self.list_widget = QListWidget()
        user_role = Qt.ItemDataRole.UserRole if IS_PYQT6 else Qt.UserRole
        checked_state = Qt.CheckState.Checked if IS_PYQT6 else Qt.Checked
        unchecked_state = Qt.CheckState.Unchecked if IS_PYQT6 else Qt.Unchecked
        checkable_flag = (
            Qt.ItemFlag.ItemIsUserCheckable
            | Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            if IS_PYQT6
            else Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable
        )

        for key in public_keys:
            fp = key.get("fingerprint", "")
            label = format_key_label(key)
            item = QListWidgetItem(label)
            item.setFlags(checkable_flag)
            item.setData(user_role, fp)
            item.setCheckState(
                checked_state if fp in selected_fps else unchecked_state
            )
            self.list_widget.addItem(item)

        layout.addWidget(self.list_widget, stretch=1)

        btn_layout = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(lambda: self._set_all_checks(True))
        btn_layout.addWidget(select_all_btn)

        clear_all_btn = QPushButton("Clear Selection")
        clear_all_btn.clicked.connect(lambda: self._set_all_checks(False))
        btn_layout.addWidget(clear_all_btn)

        btn_layout.addStretch(1)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        apply_btn = QPushButton("✓ Apply Selection")
        apply_btn.setObjectName("primaryActionBtn")
        apply_btn.clicked.connect(self._apply_selection)
        btn_layout.addWidget(apply_btn)

        layout.addLayout(btn_layout)

    def _set_all_checks(self, checked: bool) -> None:
        state = (
            (Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            if IS_PYQT6
            else (Qt.Checked if checked else Qt.Unchecked)
        )
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item is not None:
                item.setCheckState(state)

    def _apply_selection(self) -> None:
        user_role = Qt.ItemDataRole.UserRole if IS_PYQT6 else Qt.UserRole
        checked_state = Qt.CheckState.Checked if IS_PYQT6 else Qt.Checked
        chosen: list[str] = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item is not None and item.checkState() == checked_state:
                fp = item.data(user_role)
                if fp:
                    chosen.append(str(fp))

        if not chosen:
            QMessageBox.warning(
                self,
                "No Keys Selected",
                "Please check at least one saved public key, or click Cancel.",
            )
            return

        self.selected_fingerprints = chosen
        self.accept()


class GoblinTextEditor(QPlainTextEdit):
    """Scratchpad text editor that delegates file drops to the main PGPGoblinWindow."""

    def __init__(self, main_window: "PGPGoblinWindow") -> None:
        super().__init__(main_window)
        self.main_window = main_window
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: QDragEnterEvent | None) -> None:
        if event is not None and event.mimeData() is not None and event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent | None) -> None:
        if event is not None and event.mimeData() is not None and event.mimeData().hasUrls():
            urls: list[QUrl] = event.mimeData().urls()
            local_paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
            if local_paths:
                event.acceptProposedAction()
                self.main_window.handle_dropped_file(Path(local_paths[0]))
                return
        super().dropEvent(event)


class PGPGoblinWindow(QMainWindow):
    """Main window for the PGPGOBLIN scratchpad application."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PGPGOBLIN — Cryptographic PGP Scratchpad")
        self.resize(980, 720)
        self.setAcceptDrops(True)

        self.gnupg_home = get_gnupg_home()
        self.gpg = init_gpg_instance(self.gnupg_home)
        self.public_keys: list[dict[str, Any]] = []
        self.secret_keys: list[dict[str, Any]] = []

        # State for multi-saved-key selection and pasted public key
        self.multi_selected_fps: list[str] = []
        self.pasted_pubkey_armored: str = ""
        self.pasted_pubkey_summary: str = ""

        self._setup_ui()
        self._apply_styles()
        self.refresh_keys()

    def _setup_ui(self) -> None:
        """Construct the Goblin-themed cryptographic scratchpad UI."""
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(18, 16, 18, 12)
        main_layout.setSpacing(12)

        pointing_cursor = (
            Qt.CursorShape.PointingHandCursor
            if IS_PYQT6
            else Qt.PointingHandCursor
        )

        # --- Brand Header Banner ---
        header_frame = QFrame()
        header_frame.setObjectName("brandHeader")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(14, 10, 14, 10)
        header_layout.setSpacing(12)

        icon_label = QLabel()
        app_icon = resolve_app_icon()
        if not app_icon.isNull():
            icon_label.setPixmap(app_icon.pixmap(38, 38))
        header_layout.addWidget(icon_label)

        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        brand_title = QLabel("PGPGOBLIN")
        brand_title.setObjectName("brandTitle")
        brand_sub = QLabel(
            f"Native GnuPG Vault Scratchpad  •  Keyring: {self.gnupg_home}  •  Drop .asc/.gpg/.pub files anywhere"
        )
        brand_sub.setObjectName("brandSubtitle")
        title_col.addWidget(brand_title)
        title_col.addWidget(brand_sub)
        header_layout.addLayout(title_col, stretch=1)

        self.open_file_btn = QPushButton("📂 Load File...")
        self.open_file_btn.setToolTip(
            "Load a .asc, .gpg, .pgp, or .pub file into PGPGOBLIN (or drag & drop onto the window)"
        )
        self.open_file_btn.setCursor(pointing_cursor)
        self.open_file_btn.clicked.connect(self.prompt_open_file)
        header_layout.addWidget(self.open_file_btn)

        self.refresh_btn = QPushButton("↻ Reload Keyring")
        self.refresh_btn.setToolTip(f"Reload keys from {self.gnupg_home} (F5)")
        self.refresh_btn.setCursor(pointing_cursor)
        self.refresh_btn.clicked.connect(self.refresh_keys)
        header_layout.addWidget(self.refresh_btn)

        main_layout.addWidget(header_frame)

        # --- Control Card: Encryption Target & My Key Selection ---
        controls_frame = QFrame()
        controls_frame.setObjectName("controlsCard")
        controls_layout = QVBoxLayout(controls_frame)
        controls_layout.setContentsMargins(14, 12, 14, 12)
        controls_layout.setSpacing(10)

        # Row 1: Recipient Key Selection (Saved Keyring + Multi-Key Picker + Paste Public Key)
        recipient_row = QHBoxLayout()
        recipient_row.setSpacing(8)

        recipient_label = QLabel("ENCRYPT TO:")
        recipient_label.setObjectName("sectionLabel")
        recipient_label.setMinimumWidth(95)
        recipient_row.addWidget(recipient_label)

        self.recipient_combo = QComboBox()
        self.recipient_combo.setEditable(True)
        no_insert = (
            QComboBox.InsertPolicy.NoInsert if IS_PYQT6 else QComboBox.NoInsert
        )
        self.recipient_combo.setInsertPolicy(no_insert)

        completer = self.recipient_combo.completer()
        if completer is not None:
            match_contains = (
                Qt.MatchFlag.MatchContains if IS_PYQT6 else Qt.MatchContains
            )
            case_insensitive = (
                Qt.CaseSensitivity.CaseInsensitive
                if IS_PYQT6
                else Qt.CaseInsensitive
            )
            completer.setFilterMode(match_contains)
            completer.setCaseSensitivity(case_insensitive)

        if self.recipient_combo.lineEdit() is not None:
            self.recipient_combo.lineEdit().setPlaceholderText(
                "Search or select a saved encryption-capable public key..."
            )
        self.recipient_combo.setMinimumWidth(340)
        self.recipient_combo.activated.connect(self._on_single_combo_selected)
        recipient_row.addWidget(self.recipient_combo, stretch=1)

        self.multi_key_btn = QPushButton("☑ Select Saved Keys...")
        self.multi_key_btn.setToolTip(
            "Choose one or multiple saved keys from your keyring to encrypt to"
        )
        self.multi_key_btn.setCursor(pointing_cursor)
        self.multi_key_btn.clicked.connect(self.open_multi_key_dialog)
        recipient_row.addWidget(self.multi_key_btn)

        self.paste_key_btn = QPushButton("📋 Paste Public Key...")
        self.paste_key_btn.setObjectName("goldAccentBtn")
        self.paste_key_btn.setToolTip(
            "Paste a raw ASCII-armored PGP public key block to encrypt to (ephemerally or saved)"
        )
        self.paste_key_btn.setCursor(pointing_cursor)
        self.paste_key_btn.clicked.connect(self.open_paste_key_dialog)
        recipient_row.addWidget(self.paste_key_btn)

        controls_layout.addLayout(recipient_row)

        # Active Pasted Key / Multi-Key Banner (hidden unless active)
        self.override_banner = QFrame()
        self.override_banner.setObjectName("overrideBanner")
        banner_layout = QHBoxLayout(self.override_banner)
        banner_layout.setContentsMargins(12, 6, 12, 6)
        banner_layout.setSpacing(8)

        self.override_label = QLabel("")
        self.override_label.setObjectName("overrideLabel")
        banner_layout.addWidget(self.override_label, stretch=1)

        clear_override_btn = QPushButton("✕ Reset to Single Dropdown")
        clear_override_btn.setCursor(pointing_cursor)
        clear_override_btn.clicked.connect(self.reset_recipient_override)
        banner_layout.addWidget(clear_override_btn)

        self.override_banner.setVisible(False)
        controls_layout.addWidget(self.override_banner)

        # Row 2: Own Saved Key Selector ("MY KEY") + Export Public Key + Toggles
        own_key_row = QHBoxLayout()
        own_key_row.setSpacing(10)

        own_key_label = QLabel("MY KEY:")
        own_key_label.setObjectName("sectionLabel")
        own_key_label.setMinimumWidth(95)
        own_key_row.addWidget(own_key_label)

        self.own_key_combo = QComboBox()
        self.own_key_combo.setMinimumWidth(260)
        self.own_key_combo.setToolTip(
            "Select which of your personal keys in ~/.gnupg to use for signing, self-encryption, or exporting."
        )
        own_key_row.addWidget(self.own_key_combo, stretch=1)

        self.export_pub_btn = QPushButton("📤 Export My Public Key")
        self.export_pub_btn.setToolTip(
            "Export your selected 'My Key' public key block into the scratchpad and copy it to the clipboard"
        )
        self.export_pub_btn.setCursor(pointing_cursor)
        self.export_pub_btn.clicked.connect(self.export_my_public_key)
        own_key_row.addWidget(self.export_pub_btn)

        self.encrypt_to_self_cb = QCheckBox("Also encrypt to My Key")
        self.encrypt_to_self_cb.setChecked(False)
        self.encrypt_to_self_cb.setToolTip(
            "Include your selected 'My Key' as a recipient so you can also decrypt the output message."
        )
        own_key_row.addWidget(self.encrypt_to_self_cb)

        self.sign_with_my_key_cb = QCheckBox("Sign when encrypting")
        self.sign_with_my_key_cb.setChecked(False)
        self.sign_with_my_key_cb.setToolTip(
            "Cryptographically sign the encrypted message using your selected 'My Key' (via gpg-agent)."
        )
        own_key_row.addWidget(self.sign_with_my_key_cb)

        self.always_trust_cb = QCheckBox("Always trust")
        self.always_trust_cb.setChecked(True)
        self.always_trust_cb.setToolTip(
            "Allow encrypting to keys even if they haven't been locally signed in your web-of-trust."
        )
        own_key_row.addWidget(self.always_trust_cb)

        controls_layout.addLayout(own_key_row)
        main_layout.addWidget(controls_frame)

        # --- Verification / Status Alert Banner (hidden unless verifying or inspecting) ---
        self.verify_banner = QFrame()
        self.verify_banner.setObjectName("verifyBannerGood")
        verify_layout = QHBoxLayout(self.verify_banner)
        verify_layout.setContentsMargins(12, 8, 12, 8)
        verify_layout.setSpacing(10)

        self.verify_label = QLabel("")
        self.verify_label.setWordWrap(True)
        verify_layout.addWidget(self.verify_label, stretch=1)

        dismiss_verify_btn = QPushButton("✕")
        dismiss_verify_btn.setFixedWidth(32)
        dismiss_verify_btn.setCursor(pointing_cursor)
        dismiss_verify_btn.clicked.connect(lambda: self.verify_banner.setVisible(False))
        verify_layout.addWidget(dismiss_verify_btn)

        self.verify_banner.setVisible(False)
        main_layout.addWidget(self.verify_banner)

        # --- Center: Monospace Scratchpad Editor ---
        self.editor = GoblinTextEditor(self)
        self.editor.setPlaceholderText(
            "Type or paste plaintext here to encrypt or clear-sign...\n"
            "Or paste an ASCII-armored PGP MESSAGE / SIGNED MESSAGE / PUBLIC KEY block...\n"
            "Or drag & drop any .asc, .gpg, .pgp, or .pub file directly onto this pad."
        )
        mono_font = QFont("Monospace")
        style_hint = (
            QFont.StyleHint.Monospace if IS_PYQT6 else QFont.Monospace
        )
        mono_font.setStyleHint(style_hint)
        mono_font.setPointSize(11)
        self.editor.setFont(mono_font)
        main_layout.addWidget(self.editor, stretch=1)

        # --- Bottom Bar: Cryptographic Actions & Scratchpad Utilities ---
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(8)

        self.encrypt_btn = QPushButton("🔒 Encrypt")
        self.encrypt_btn.setObjectName("primaryActionBtn")
        self.encrypt_btn.setToolTip("Encrypt scratchpad text to selected recipient(s) (Ctrl+E)")
        self.encrypt_btn.setCursor(pointing_cursor)
        self.encrypt_btn.clicked.connect(self.encrypt_text)
        actions_layout.addWidget(self.encrypt_btn)

        self.sym_encrypt_btn = QPushButton("🔑 Symmetric")
        self.sym_encrypt_btn.setObjectName("goldAccentBtn")
        self.sym_encrypt_btn.setToolTip(
            "Encrypt with a shared passphrase via system pinentry instead of a public key (Ctrl+Shift+E)"
        )
        self.sym_encrypt_btn.setCursor(pointing_cursor)
        self.sym_encrypt_btn.clicked.connect(self.encrypt_symmetric)
        actions_layout.addWidget(self.sym_encrypt_btn)

        self.decrypt_btn = QPushButton("🔓 Decrypt")
        self.decrypt_btn.setObjectName("secondaryActionBtn")
        self.decrypt_btn.setToolTip(
            "Decrypt PGP block in scratchpad via system gpg-agent / pinentry (Ctrl+D)"
        )
        self.decrypt_btn.setCursor(pointing_cursor)
        self.decrypt_btn.clicked.connect(self.decrypt_text)
        actions_layout.addWidget(self.decrypt_btn)

        self.clearsign_btn = QPushButton("✍ Clear-Sign")
        self.clearsign_btn.setToolTip(
            "Wrap plaintext in a -----BEGIN PGP SIGNED MESSAGE----- block using 'My Key' (Ctrl+S)"
        )
        self.clearsign_btn.setCursor(pointing_cursor)
        self.clearsign_btn.clicked.connect(self.clearsign_text)
        actions_layout.addWidget(self.clearsign_btn)

        self.verify_btn = QPushButton("✓ Verify Sig")
        self.verify_btn.setToolTip(
            "Verify the cryptographic signature of a PGP SIGNED MESSAGE in the scratchpad (Ctrl+Shift+V)"
        )
        self.verify_btn.setCursor(pointing_cursor)
        self.verify_btn.clicked.connect(self.verify_text)
        actions_layout.addWidget(self.verify_btn)

        actions_layout.addStretch(1)

        self.copy_btn = QPushButton("📋 Copy")
        self.copy_btn.setToolTip("Copy entire scratchpad content to clipboard (Ctrl+Shift+C)")
        self.copy_btn.setCursor(pointing_cursor)
        self.copy_btn.clicked.connect(self.copy_to_clipboard)
        actions_layout.addWidget(self.copy_btn)

        self.clear_btn = QPushButton("✕ Clear")
        self.clear_btn.setObjectName("dangerBtn")
        self.clear_btn.setToolTip("Clear scratchpad editor (Ctrl+L)")
        self.clear_btn.setCursor(pointing_cursor)
        self.clear_btn.clicked.connect(self.clear_editor)
        actions_layout.addWidget(self.clear_btn)

        main_layout.addLayout(actions_layout)

        # --- Status Bar ---
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # --- Keyboard Shortcuts ---
        self._bind_shortcut("Ctrl+E", self.encrypt_text)
        self._bind_shortcut("Ctrl+Shift+E", self.encrypt_symmetric)
        self._bind_shortcut("Ctrl+D", self.decrypt_text)
        self._bind_shortcut("Ctrl+S", self.clearsign_text)
        self._bind_shortcut("Ctrl+Shift+V", self.verify_text)
        self._bind_shortcut("Ctrl+Shift+C", self.copy_to_clipboard)
        self._bind_shortcut("Ctrl+L", self.clear_editor)
        self._bind_shortcut("F5", self.refresh_keys)

    def _bind_shortcut(self, sequence: str, callback: Any) -> None:
        action = QAction(self)
        action.setShortcut(QKeySequence(sequence))
        action.triggered.connect(callback)
        self.addAction(action)

    def _apply_styles(self) -> None:
        """Apply the PGPGOBLIN Dark Alchemical / Obsidian-Emerald-Gold theme."""
        self.setStyleSheet(
            """
            QMainWindow, QDialog {
                background-color: #0d130f;
            }
            QFrame#brandHeader {
                background-color: #121b15;
                border: 1px solid #223628;
                border-left: 4px solid #34d399;
                border-radius: 8px;
            }
            QLabel#brandTitle {
                color: #34d399;
                font-size: 17px;
                font-weight: 800;
                letter-spacing: 1.5px;
            }
            QLabel#brandSubtitle {
                color: #8ca895;
                font-size: 11px;
            }
            QFrame#controlsCard {
                background-color: #131c16;
                border: 1px solid #233629;
                border-radius: 8px;
            }
            QFrame#overrideBanner {
                background-color: #192b1f;
                border: 1px solid #2f6e46;
                border-radius: 6px;
            }
            QFrame#verifyBannerGood {
                background-color: #132a1c;
                border: 1px solid #2ea062;
                border-left: 4px solid #34d399;
                border-radius: 6px;
            }
            QFrame#verifyBannerWarn {
                background-color: #2b2112;
                border: 1px solid #9e6f1e;
                border-left: 4px solid #f59e0b;
                border-radius: 6px;
            }
            QFrame#verifyBannerBad {
                background-color: #2d1416;
                border: 1px solid #962d37;
                border-left: 4px solid #ef4444;
                border-radius: 6px;
            }
            QLabel, QCheckBox {
                color: #dce7df;
                font-size: 13px;
            }
            QLabel#sectionLabel {
                font-weight: 800;
                font-size: 11px;
                letter-spacing: 0.8px;
                color: #6ee7b7;
            }
            QLabel#overrideLabel {
                color: #a7f3d0;
                font-weight: 600;
            }
            QComboBox {
                background-color: #18241c;
                color: #ecfdf5;
                border: 1px solid #2c4434;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 13px;
            }
            QComboBox:focus {
                border: 1px solid #34d399;
            }
            QComboBox QAbstractItemView, QListWidget {
                background-color: #141f18;
                color: #ecfdf5;
                selection-background-color: #1e4d33;
                selection-color: #ffffff;
                border: 1px solid #2c4434;
                border-radius: 6px;
                padding: 4px;
            }
            QPlainTextEdit {
                background-color: #090d0a;
                color: #d1fae5;
                border: 1px solid #233829;
                border-radius: 8px;
                padding: 12px;
                selection-background-color: #1f5437;
            }
            QPlainTextEdit:focus {
                border: 1px solid #34d399;
            }
            QPushButton {
                background-color: #19261d;
                color: #dce7df;
                border: 1px solid #2d4535;
                border-radius: 6px;
                padding: 8px 13px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #223528;
                border-color: #3f634c;
            }
            QPushButton:pressed {
                background-color: #111a14;
            }
            QPushButton#primaryActionBtn {
                background-color: #186339;
                border-color: #289457;
                color: #ffffff;
            }
            QPushButton#primaryActionBtn:hover {
                background-color: #1f7a47;
                border-color: #34d399;
            }
            QPushButton#secondaryActionBtn {
                background-color: #184e59;
                border-color: #257687;
                color: #ffffff;
            }
            QPushButton#secondaryActionBtn:hover {
                background-color: #1f6370;
                border-color: #38bdf8;
            }
            QPushButton#goldAccentBtn {
                background-color: #382a11;
                border-color: #78581d;
                color: #fde68a;
            }
            QPushButton#goldAccentBtn:hover {
                background-color: #4d3916;
                border-color: #f59e0b;
            }
            QPushButton#dangerBtn:hover {
                background-color: #691e24;
                border-color: #b93843;
                color: #ffffff;
            }
            QStatusBar {
                color: #84a38d;
                font-size: 12px;
            }
            """
        )

    def _show_error(self, title: str, message: str, details: str = "") -> None:
        """Display a clean, non-intrusive modal error dialog."""
        dialog = QMessageBox(self)
        warning_icon = (
            QMessageBox.Icon.Warning if IS_PYQT6 else QMessageBox.Warning
        )
        dialog.setIcon(warning_icon)
        dialog.setWindowTitle(title)
        dialog.setText(message)
        if details:
            dialog.setDetailedText(details.strip())
        if hasattr(dialog, "exec"):
            dialog.exec()
        else:
            dialog.exec_()

    def _show_verify_banner(self, message: str, level: str = "good") -> None:
        """Display the signature verification / status banner above the editor."""
        obj_name = {
            "good": "verifyBannerGood",
            "warn": "verifyBannerWarn",
            "bad": "verifyBannerBad",
        }.get(level, "verifyBannerGood")
        self.verify_banner.setObjectName(obj_name)
        self.verify_banner.style().unpolish(self.verify_banner)
        self.verify_banner.style().polish(self.verify_banner)
        self.verify_label.setText(message)
        self.verify_banner.setVisible(True)

    # --- Drag & Drop / File Open Support ---
    def dragEnterEvent(self, event: QDragEnterEvent | None) -> None:
        if event is not None and event.mimeData() is not None and event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent | None) -> None:
        if event is not None and event.mimeData() is not None and event.mimeData().hasUrls():
            urls: list[QUrl] = event.mimeData().urls()
            local_paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
            if local_paths:
                event.acceptProposedAction()
                self.handle_dropped_file(Path(local_paths[0]))
                return
        super().dropEvent(event)

    def prompt_open_file(self) -> None:
        """Open a file chooser for .asc, .gpg, .pgp, .pub, or text files."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open PGP or Text File",
            str(Path.home()),
            "PGP & Text Files (*.asc *.gpg *.pgp *.pub *.txt *.sig *);;All Files (*)",
        )
        if file_path:
            self.handle_dropped_file(Path(file_path))

    def handle_dropped_file(self, path: Path) -> None:
        """Inspect a dropped/opened file and route public keys, binary .gpg, or text appropriately."""
        if not path.is_file():
            self._show_error("File Not Found", f"Could not read file: {path}")
            return

        try:
            raw_bytes = path.read_bytes()
        except Exception as exc:
            self._show_error("File Read Error", f"Failed to read {path.name}.", str(exc))
            return

        # Attempt UTF-8 decode first
        try:
            text_content = raw_bytes.decode("utf-8")
            is_text = True
        except UnicodeDecodeError:
            text_content = ""
            is_text = False

        # 1. If the file is an ASCII-armored Public Key block, load it into Paste Public Key flow
        if is_text and "-----BEGIN PGP PUBLIC KEY BLOCK-----" in text_content:
            dlg = PastePublicKeyDialog(self, initial_key=text_content.strip())
            accepted = dlg.exec() if hasattr(dlg, "exec") else dlg.exec_()
            if accepted:
                self._apply_paste_dialog_result(dlg)
            return

        # 2. If it's a binary .gpg/.pgp file, offer immediate decryption via GnuPG
        if not is_text:
            self.status_bar.showMessage(f"Decrypting binary file {path.name} via gpg-agent...")
            QApplication.processEvents()
            decrypted = self.gpg.decrypt(raw_bytes)
            if decrypted.ok:
                plaintext = decrypted.data.decode("utf-8", errors="replace")
                self.editor.setPlainText(plaintext)
                self._check_embedded_signature(decrypted)
                self.status_bar.showMessage(f"Decrypted binary file: {path.name}")
            else:
                self._show_error(
                    "Binary File Decryption Failed",
                    f"GnuPG could not decrypt binary file '{path.name}' ({getattr(decrypted, 'status', 'failed')}).",
                    getattr(decrypted, "stderr", ""),
                )
            return

        # 3. Otherwise load text content (.asc message, clear-signed block, or plaintext) into scratchpad
        self.editor.setPlainText(text_content)
        self.status_bar.showMessage(f"Loaded {path.name} into scratchpad.")

    def refresh_keys(self) -> None:
        """Discover all public and secret keys from the native system GnuPG keyring."""
        previous_pub_fp = self.recipient_combo.currentData()
        previous_sec_fp = self.own_key_combo.currentData()

        self.recipient_combo.clear()
        self.own_key_combo.clear()

        try:
            pub_keys = self.gpg.list_keys(False)
            sec_keys = self.gpg.list_keys(True)
        except Exception as exc:
            self._show_error(
                "Keyring Error",
                f"Failed to read GnuPG keyring from {self.gnupg_home}.",
                str(exc),
            )
            self.status_bar.showMessage("Error loading GnuPG keyring.")
            return

        valid_pub = [k for k in pub_keys if is_usable_key(k, require_encrypt=True)]
        valid_sec = [k for k in sec_keys if is_usable_key(k, require_encrypt=False)]
        self.public_keys = valid_pub
        self.secret_keys = valid_sec

        # Populate recipient public keys combo
        restored_pub_idx = -1
        for key in valid_pub:
            fp = key.get("fingerprint", "")
            self.recipient_combo.addItem(format_key_label(key), userData=fp)
            if previous_pub_fp and fp == previous_pub_fp:
                restored_pub_idx = self.recipient_combo.count() - 1

        if restored_pub_idx >= 0:
            self.recipient_combo.setCurrentIndex(restored_pub_idx)
        elif self.recipient_combo.count() > 0:
            self.recipient_combo.setCurrentIndex(0)

        # Populate user's secret keys combo ("My Key")
        restored_sec_idx = -1
        for key in valid_sec:
            fp = key.get("fingerprint", "")
            self.own_key_combo.addItem(format_key_label(key), userData=fp)
            if previous_sec_fp and fp == previous_sec_fp:
                restored_sec_idx = self.own_key_combo.count() - 1

        if self.own_key_combo.count() == 0:
            self.own_key_combo.addItem("<No secret keys in ~/.gnupg>", userData="")
            self.encrypt_to_self_cb.setEnabled(False)
            self.sign_with_my_key_cb.setEnabled(False)
            self.export_pub_btn.setEnabled(False)
            self.clearsign_btn.setEnabled(False)
        else:
            self.encrypt_to_self_cb.setEnabled(True)
            self.sign_with_my_key_cb.setEnabled(True)
            self.export_pub_btn.setEnabled(True)
            self.clearsign_btn.setEnabled(True)
            if restored_sec_idx >= 0:
                self.own_key_combo.setCurrentIndex(restored_sec_idx)
            else:
                self.own_key_combo.setCurrentIndex(0)

        self.status_bar.showMessage(
            f"Vault Ready — {len(valid_pub)} encryption-capable public key(s), {len(valid_sec)} personal secret key(s)"
        )

    def _on_single_combo_selected(self, _index: int) -> None:
        if self.multi_selected_fps or self.pasted_pubkey_armored:
            self.reset_recipient_override()

    def reset_recipient_override(self) -> None:
        """Return to standard single-recipient dropdown mode."""
        self.multi_selected_fps = []
        self.pasted_pubkey_armored = ""
        self.pasted_pubkey_summary = ""
        self.override_banner.setVisible(False)
        self.recipient_combo.setEnabled(True)
        self.status_bar.showMessage("Using single saved key dropdown.")

    def _update_override_banner(self) -> None:
        parts: list[str] = []
        if self.pasted_pubkey_armored:
            parts.append(f"Pasted Key: {self.pasted_pubkey_summary}")
        if self.multi_selected_fps:
            parts.append(f"{len(self.multi_selected_fps)} Saved Key(s) Selected")

        if parts:
            self.override_label.setText("Active Encryption Target — " + "  +  ".join(parts))
            self.override_banner.setVisible(True)
        else:
            self.override_banner.setVisible(False)

    def open_multi_key_dialog(self) -> None:
        if not self.public_keys:
            self._show_error(
                "No Saved Keys",
                f"No encryption-capable public keys were found in {self.gnupg_home}. Use 'Paste Public Key...' instead.",
            )
            return

        current_selection = list(self.multi_selected_fps)
        if not current_selection:
            single_fp = self._resolve_single_combo_recipient()
            if single_fp:
                current_selection = [single_fp]

        dlg = MultiRecipientDialog(self.public_keys, current_selection, self)
        accepted = dlg.exec() if hasattr(dlg, "exec") else dlg.exec_()
        if accepted:
            self.multi_selected_fps = dlg.selected_fingerprints
            if len(self.multi_selected_fps) == 1 and not self.pasted_pubkey_armored:
                fp = self.multi_selected_fps[0]
                for i in range(self.recipient_combo.count()):
                    if self.recipient_combo.itemData(i) == fp:
                        self.recipient_combo.setCurrentIndex(i)
                        break
                self.multi_selected_fps = []
                self._update_override_banner()
                self.status_bar.showMessage(f"Selected saved key [{fp[-8:]}].")
            else:
                self._update_override_banner()
                self.status_bar.showMessage(
                    f"Selected {len(self.multi_selected_fps)} saved key(s) for encryption."
                )

    def open_paste_key_dialog(self) -> None:
        dlg = PastePublicKeyDialog(self, initial_key=self.pasted_pubkey_armored)
        accepted = dlg.exec() if hasattr(dlg, "exec") else dlg.exec_()
        if accepted:
            self._apply_paste_dialog_result(dlg)

    def _apply_paste_dialog_result(self, dlg: PastePublicKeyDialog) -> None:
        if dlg.save_to_keyring:
            import_res = self.gpg.import_keys(dlg.pasted_armored_key)
            imported_fps = getattr(import_res, "fingerprints", []) or []
            self.pasted_pubkey_armored = ""
            self.pasted_pubkey_summary = ""
            self.refresh_keys()
            if imported_fps:
                target_fp = imported_fps[0]
                for i in range(self.recipient_combo.count()):
                    if self.recipient_combo.itemData(i) == target_fp:
                        self.recipient_combo.setCurrentIndex(i)
                        break
            self._update_override_banner()
            self.status_bar.showMessage(
                f"Imported key ({dlg.detected_summary}) into {self.gnupg_home}."
            )
        else:
            self.pasted_pubkey_armored = dlg.pasted_armored_key
            self.pasted_pubkey_summary = dlg.detected_summary
            self._update_override_banner()
            self.status_bar.showMessage(
                f"Using pasted public key: {dlg.detected_summary} (ephemeral)."
            )

    def export_my_public_key(self) -> None:
        """One-click export of the selected 'My Key' ASCII-armored public key block."""
        own_fp = str(self.own_key_combo.currentData() or "")
        if not own_fp:
            self._show_error(
                "No Personal Key Selected",
                "No secret key is available in 'My Key' to export.",
            )
            return

        try:
            armored_pubkey = self.gpg.export_keys(own_fp, False, armor=True)
        except TypeError:
            armored_pubkey = self.gpg.export_keys(own_fp)

        if not armored_pubkey or "-----BEGIN PGP PUBLIC KEY BLOCK-----" not in armored_pubkey:
            self._show_error(
                "Export Failed",
                f"Could not export public key for fingerprint {own_fp}.",
            )
            return

        self.editor.setPlainText(armored_pubkey.strip() + "\n")
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(armored_pubkey.strip() + "\n")

        self.status_bar.showMessage(
            f"Exported Public Key [{own_fp[-8:]}] to scratchpad and copied to clipboard."
        )

    def _resolve_single_combo_recipient(self) -> str | None:
        if self.recipient_combo.count() == 0:
            return None

        idx = self.recipient_combo.currentIndex()
        current_text = self.recipient_combo.currentText().strip()

        if idx >= 0 and self.recipient_combo.itemText(idx) == current_text:
            fp = self.recipient_combo.itemData(idx)
            if fp:
                return str(fp)

        if current_text:
            lowered = current_text.lower()
            for i in range(self.recipient_combo.count()):
                item_text = self.recipient_combo.itemText(i).lower()
                item_fp = str(self.recipient_combo.itemData(i) or "")
                if lowered in item_text or lowered in item_fp.lower():
                    self.recipient_combo.setCurrentIndex(i)
                    return item_fp

        return None

    def encrypt_text(self) -> None:
        """Encrypt the scratchpad contents using saved key(s) and/or a pasted public key."""
        self.verify_banner.setVisible(False)
        raw_text = self.editor.toPlainText()
        if not raw_text.strip():
            self._show_error(
                "Empty Scratchpad",
                "Please enter or paste some text in the scratchpad before encrypting.",
            )
            return

        own_fp = str(self.own_key_combo.currentData() or "")
        sign_fp = own_fp if (self.sign_with_my_key_cb.isChecked() and own_fp) else None

        saved_recipients: list[str] = []
        if self.multi_selected_fps:
            saved_recipients.extend(self.multi_selected_fps)
        elif not self.pasted_pubkey_armored:
            single_fp = self._resolve_single_combo_recipient()
            if single_fp:
                saved_recipients.append(single_fp)

        if self.encrypt_to_self_cb.isChecked() and own_fp:
            # Verify own key is encryption-capable before adding
            own_pub = next((k for k in self.public_keys if k.get("fingerprint") == own_fp), None)
            if own_pub is None:
                self._show_error(
                    "My Key Cannot Encrypt",
                    f"Your selected key [{own_fp[-8:]}] does not have an encryption-capable subkey.\n"
                    "Uncheck 'Also encrypt to My Key' or add an encryption subkey in GnuPG.",
                )
                return
            if own_fp not in saved_recipients:
                saved_recipients.append(own_fp)

        if self.pasted_pubkey_armored:
            if sign_fp:
                self._show_error(
                    "Save Key Required for Signing",
                    "To cryptographically sign with your secret key while encrypting to a pasted key, "
                    "please check 'Also import & save this key into my system keyring' in the Paste Public Key dialog.",
                )
                return
            self._encrypt_with_ephemeral_pubkey(raw_text, saved_recipients)
            return

        if not saved_recipients:
            self._show_error(
                "No Recipient Selected",
                "Please select a saved public key from your keyring, or click 'Paste Public Key...'.",
            )
            return

        try:
            encrypt_kwargs: dict[str, Any] = {
                "recipients": saved_recipients,
                "always_trust": self.always_trust_cb.isChecked(),
                "armor": True,
            }
            if sign_fp:
                encrypt_kwargs["sign"] = sign_fp

            encrypted = self.gpg.encrypt(raw_text, **encrypt_kwargs)
        except Exception as exc:
            self._show_error(
                "Encryption Exception",
                "An unexpected error occurred while invoking GnuPG.",
                str(exc),
            )
            return

        if not encrypted.ok or not str(encrypted).strip():
            status_msg = getattr(encrypted, "status", "Unknown status")
            stderr_msg = getattr(encrypted, "stderr", "")
            self._show_error(
                "Encryption Failed",
                f"GnuPG could not encrypt the message ({status_msg}).\n\n"
                "Ensure the selected key(s) have encryption-capable subkeys and are valid.",
                stderr_msg,
            )
            self.status_bar.showMessage(f"Encryption failed: {status_msg}")
            return

        self.editor.setPlainText(str(encrypted))
        short_list = ", ".join(fp[-8:] for fp in saved_recipients)
        signed_note = f" (signed with [{sign_fp[-8:]}])" if sign_fp else ""
        self.status_bar.showMessage(
            f"Encrypted to [{short_list}]{signed_note}"
        )

    def _encrypt_with_ephemeral_pubkey(
        self, raw_text: str, extra_saved_fps: list[str]
    ) -> None:
        tmp_dir = tempfile.mkdtemp(prefix="pgpgoblin_ephem_")
        try:
            temp_gpg = init_gpg_instance(tmp_dir)
            imp_res = temp_gpg.import_keys(self.pasted_pubkey_armored)
            target_fps = list(getattr(imp_res, "fingerprints", []) or [])

            for saved_fp in extra_saved_fps:
                exported = self.gpg.export_keys(saved_fp)
                if exported:
                    temp_gpg.import_keys(exported)
                    if saved_fp not in target_fps:
                        target_fps.append(saved_fp)

            if not target_fps:
                self._show_error(
                    "Invalid Pasted Key",
                    "Could not extract a valid recipient fingerprint from the pasted public key.",
                )
                return

            encrypted = temp_gpg.encrypt(
                raw_text,
                recipients=target_fps,
                always_trust=True,
                armor=True,
            )
        except Exception as exc:
            self._show_error(
                "Encryption Exception",
                "An unexpected error occurred while encrypting with the pasted key.",
                str(exc),
            )
            return
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        if not encrypted.ok or not str(encrypted).strip():
            status_msg = getattr(encrypted, "status", "Unknown status")
            stderr_msg = getattr(encrypted, "stderr", "")
            self._show_error(
                "Encryption Failed",
                f"GnuPG could not encrypt to the pasted public key ({status_msg}).",
                stderr_msg,
            )
            self.status_bar.showMessage(f"Encryption failed: {status_msg}")
            return

        self.editor.setPlainText(str(encrypted))
        short_list = ", ".join(fp[-8:] for fp in target_fps)
        self.status_bar.showMessage(
            f"Encrypted to pasted key [{short_list}]"
        )

    def encrypt_symmetric(self) -> None:
        """Encrypt the scratchpad contents with a symmetric passphrase via system pinentry."""
        self.verify_banner.setVisible(False)
        raw_text = self.editor.toPlainText()
        if not raw_text.strip():
            self._show_error(
                "Empty Scratchpad",
                "Please enter or paste some text in the scratchpad before encrypting symmetrically.",
            )
            return

        self.status_bar.showMessage("Requesting passphrase via gpg-agent / pinentry...")
        QApplication.processEvents()

        try:
            encrypted = self.gpg.encrypt(
                raw_text,
                recipients=None,
                symmetric="AES256",
                armor=True,
            )
        except Exception as exc:
            self._show_error(
                "Symmetric Encryption Exception",
                "An unexpected error occurred while invoking GnuPG symmetric encryption.",
                str(exc),
            )
            return

        if not encrypted.ok or not str(encrypted).strip():
            status_msg = getattr(encrypted, "status", "symmetric encryption failed")
            stderr_msg = getattr(encrypted, "stderr", "")
            self._show_error(
                "Symmetric Encryption Failed",
                f"GnuPG could not symmetrically encrypt the message ({status_msg}).\n"
                "Check that pinentry passphrase confirmation succeeded.",
                stderr_msg,
            )
            self.status_bar.showMessage(f"Symmetric encryption failed: {status_msg}")
            return

        self.editor.setPlainText(str(encrypted))
        self.status_bar.showMessage("Encrypted symmetrically (AES-256) via gpg-agent.")

    def clearsign_text(self) -> None:
        """Clear-sign the scratchpad plaintext using the selected 'My Key'."""
        self.verify_banner.setVisible(False)
        raw_text = self.editor.toPlainText()
        if not raw_text.strip():
            self._show_error(
                "Empty Scratchpad",
                "Please enter some plaintext in the scratchpad to clear-sign.",
            )
            return

        own_fp = str(self.own_key_combo.currentData() or "")
        if not own_fp:
            self._show_error(
                "No Personal Key Selected",
                "No secret key is selected in 'My Key' to sign with.",
            )
            return

        self.status_bar.showMessage(f"Signing with [{own_fp[-8:]}] via gpg-agent...")
        QApplication.processEvents()

        try:
            signed = self.gpg.sign(raw_text, keyid=own_fp, clearsign=True)
        except Exception as exc:
            self._show_error(
                "Signing Exception",
                "An unexpected error occurred while invoking GnuPG clear-sign.",
                str(exc),
            )
            return

        if not getattr(signed, "data", b"") or "-----BEGIN PGP SIGNED MESSAGE-----" not in str(signed):
            status_msg = getattr(signed, "status", "signing failed")
            stderr_msg = getattr(signed, "stderr", "")
            self._show_error(
                "Clear-Sign Failed",
                f"GnuPG could not sign the message ({status_msg}).\n"
                "Verify that pinentry authentication succeeded.",
                stderr_msg,
            )
            self.status_bar.showMessage(f"Signing failed: {status_msg}")
            return

        self.editor.setPlainText(str(signed))
        self.status_bar.showMessage(f"Clear-signed message with key [{own_fp[-8:]}].")

    def verify_text(self) -> None:
        """Verify an ASCII-armored PGP SIGNED MESSAGE in the scratchpad."""
        armored_text = self.editor.toPlainText()
        if not armored_text.strip():
            self._show_error(
                "Empty Scratchpad",
                "Paste a '-----BEGIN PGP SIGNED MESSAGE-----' block into the scratchpad to verify.",
            )
            return

        if "-----BEGIN PGP SIGNED MESSAGE-----" not in armored_text and "-----BEGIN PGP MESSAGE-----" not in armored_text:
            self._show_error(
                "No Signed PGP Block Found",
                "No '-----BEGIN PGP SIGNED MESSAGE-----' header was found in the scratchpad.",
            )
            return

        try:
            verified = self.gpg.verify(armored_text.encode("utf-8"))
        except Exception as exc:
            self._show_error(
                "Verification Exception",
                "An unexpected error occurred while verifying the signature.",
                str(exc),
            )
            return

        if verified.valid:
            signer = getattr(verified, "username", None) or "Unknown UID"
            fp = getattr(verified, "pubkey_fingerprint", None) or getattr(verified, "fingerprint", "") or ""
            trust_text = getattr(verified, "trust_text", "") or ""
            trust_note = f"  •  Trust: {trust_text}" if trust_text else ""
            self._show_verify_banner(
                f"✓ VALID PGP SIGNATURE — Signed by: {signer}  [{fp[-16:] if fp else 'N/A'}]{trust_note}",
                level="good",
            )
            self.status_bar.showMessage(f"Valid signature from {signer}")
        else:
            status_msg = getattr(verified, "status", "invalid or missing public key")
            key_id = getattr(verified, "key_id", "") or ""
            key_note = f" (Key ID: {key_id})" if key_id else ""
            self._show_verify_banner(
                f"⚠ SIGNATURE NOT VERIFIED — Status: {status_msg}{key_note}. "
                "Ensure the signer's public key is imported in ~/.gnupg and the message was not modified.",
                level="bad",
            )
            self.status_bar.showMessage(f"Signature verification failed: {status_msg}")

    def _check_embedded_signature(self, decrypted: Any) -> None:
        """If a decrypted message also contained a signature, show a verification banner."""
        if getattr(decrypted, "valid", False):
            signer = getattr(decrypted, "username", None) or "Unknown UID"
            fp = getattr(decrypted, "pubkey_fingerprint", None) or getattr(decrypted, "fingerprint", "") or ""
            self._show_verify_banner(
                f"✓ DECRYPTED & VERIFIED SIGNATURE — Signed by: {signer}  [{fp[-16:] if fp else 'N/A'}]",
                level="good",
            )
        elif getattr(decrypted, "key_id", None):
            key_id = getattr(decrypted, "key_id", "")
            status_msg = getattr(decrypted, "trust_text", None) or getattr(decrypted, "status", "unverified")
            self._show_verify_banner(
                f"ℹ Decrypted message included a signature from Key ID [{key_id}] ({status_msg}).",
                level="warn",
            )
        else:
            self.verify_banner.setVisible(False)

    def decrypt_text(self) -> None:
        """Decrypt an ASCII-armored PGP message in the scratchpad via system gpg-agent."""
        armored_text = self.editor.toPlainText()
        if not armored_text.strip():
            self._show_error(
                "Empty Scratchpad",
                "Please paste an ASCII-armored PGP message into the scratchpad to decrypt.",
            )
            return

        if "-----BEGIN PGP MESSAGE-----" not in armored_text:
            self._show_error(
                "Invalid PGP Block",
                "No '-----BEGIN PGP MESSAGE-----' header found in the scratchpad.",
            )
            return

        self.status_bar.showMessage("Decrypting via GnuPG / gpg-agent...")
        QApplication.processEvents()

        try:
            decrypted = self.gpg.decrypt(armored_text)
        except Exception as exc:
            self._show_error(
                "Decryption Exception",
                "An unexpected error occurred while invoking GnuPG.",
                str(exc),
            )
            return

        if not decrypted.ok:
            status_msg = getattr(decrypted, "status", "decryption failed")
            stderr_msg = getattr(decrypted, "stderr", "")
            self._show_error(
                "Decryption Failed",
                f"GnuPG could not decrypt the message ({status_msg}).\n\n"
                "Verify that you possess the matching secret key (or symmetric passphrase) and that "
                "pinentry authentication succeeded.",
                stderr_msg,
            )
            self.status_bar.showMessage(f"Decryption failed: {status_msg}")
            return

        plaintext = decrypted.data.decode("utf-8", errors="replace")
        self.editor.setPlainText(plaintext)
        self._check_embedded_signature(decrypted)
        self.status_bar.showMessage("Message decrypted.")

    def copy_to_clipboard(self) -> None:
        """Copy the entire scratchpad content to the system clipboard."""
        text = self.editor.toPlainText()
        if not text:
            self.status_bar.showMessage("Scratchpad is empty — nothing to copy.")
            return

        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
            self.status_bar.showMessage("Copied scratchpad content to clipboard.")

    def clear_editor(self) -> None:
        """Clear the scratchpad editor and hide verification banners."""
        self.editor.clear()
        self.verify_banner.setVisible(False)
        self.editor.setFocus()
        self.status_bar.showMessage("Scratchpad cleared.")


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("pgpgoblin")
    app.setApplicationDisplayName("PGPGOBLIN")
    if hasattr(app, "setDesktopFileName"):
        app.setDesktopFileName("pgpgoblin")

    icon = resolve_app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)

    window = PGPGoblinWindow()
    window.show()
    if hasattr(app, "exec"):
        return app.exec()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
