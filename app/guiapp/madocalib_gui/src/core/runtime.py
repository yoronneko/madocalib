# Copyright (C) 2026 Cabinet Office, Japan, All rights reserved.
# Copyright (C) 2026 Lighthouse Technology & Consulting Co. Ltd., All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause
"""Runtime utilities and global configuration management.

Notes:
    - Detects PyInstaller frozen mode.
    - Provides base_dir, resource paths, and settings persistence.
    - Windows platform assumed for encoding and path layout.

"""

import locale
import logging
import sys
import tkinter
from pathlib import Path

import constants as g
from services.settings_service import AppSettings, SettingsService
from ui.eventbus import post

logger = logging.getLogger(__name__)

_ss: SettingsService | None = None  # process-wide config service


def get_base_dir() -> Path:
    """Resolve the application base directory.

    Notes:
        - In frozen (PyInstaller) mode, use the executable's directory.
        - Otherwise, walk up from this file to the project root.

    """
    if getattr(sys, "frozen", False):
        base_dir = Path(sys.executable).resolve().parent.parent
    else:
        base_dir = Path(__file__).resolve().parent
        p = Path(__file__).resolve().parent
        for _ in range(8):
            if (p / "bin").exists() and (p / "app").exists():
                base_dir = p
                break
            p = p.parent

    logger.debug("base=%s", str(base_dir))
    return base_dir


def resource_path(rel: str) -> str:
    """Return an absolute resource path.

    Args:
        rel (str): Relative path inside the bundle or source tree.

    Returns:
        str: Absolute path string.

    """
    if hasattr(sys, "_MEIPASS"):
        base_dir = Path(sys._MEIPASS)
    else:
        base_dir = Path(__file__).resolve().parent.parent
    return str((base_dir / rel))


def set_window_icon(window) -> None:
    """Set the window icon if available; ignore failures.

    Args:
        window: A Tk or Toplevel window.

    """
    try:
        window.iconbitmap(resource_path("resources/icon.ico"))
    except tkinter.TclError as e:
        logger.debug("icon set failed: %r", e)


def init_settings() -> None:
    """Initialize and load the application settings once (idempotent)."""
    global _ss
    if _ss is not None:
        return
    ini_file = (get_base_dir() / g.PATH_INI_MADOCALIBGUI).resolve()
    ss = SettingsService(ini_file)
    ss.load()
    _ss = ss


def save_settings() -> None:
    """Persist the current application settings if available."""
    if _ss is None:
        return
    try:
        _ss.save()
    except Exception as e:
        logger.error(".ini save failed: %s", e)


def get_settings() -> AppSettings | None:
    """Return the in-memory settings or `None` if uninitialized."""
    if _ss is None:
        return None
    return _ss.data


def set_settings(settings: AppSettings) -> None:
    """Replace the in-memory `AppSettings` with the given one."""
    if _ss is None:
        return
    _ss.data = settings


def update_conf_file(filepath: str) -> None:
    """Update `settings.inputs.conf_path` with `filepath` if available."""
    if _ss is not None:
        _ss.data.inputs.conf_path = filepath


def get_conf_path() -> str:
    """Return the active configuration path, falling back to default.

    Returns:
        str: Resolved configuration path.

    Notes:
        Updates in-memory settings if fallback occurs and logs the path.

    """
    if _ss is None:
        return ""
    conf = _ss.data.inputs.conf_path
    default_conf = (get_base_dir() / g.PATH_CONF_DEFAULT).resolve()
    if not Path(conf).is_file():
        if default_conf.is_file():
            _ss.data.inputs.conf_path = str(default_conf)
            conf = str(default_conf)
            post(
                "message",
                level="warning",
                text=(
                    "Failed to load the conf file, using the "
                    f'"{g.PATH_CONF_DEFAULT}" instead.'
                ),
            )
        else:
            post(
                "message",
                level="warning",
                text="Warning: No such conf file.",
            )
    # Log the resolved path for diagnostics.
    logger.info("conf=%s", conf)
    return conf


def get_bat_path() -> Path:
    """Return absolute path to the `rnx2rtkp` batch file."""
    return (get_base_dir() / g.PATH_BAT_RNX2RTKP).resolve()


def get_rtkplot_path() -> Path | None:
    """Return absolute path to `rtkplot.exe` if it exists; otherwise `None`."""
    path = (get_base_dir() / g.PATH_BIN_RTKPLOT).resolve()
    return path if path.is_file() else None


def get_rnx2rtkp_path() -> Path | None:
    """Return absolute path to `rnx2rtkp.exe` if it exists; otherwise `None`."""
    path = (get_base_dir() / g.PATH_BIN_RNX2RTKP).resolve()
    return path if path.is_file() else None


def supports_unicode(target_chars: str) -> bool:
    """Return True if current stdout encoding can encode given characters.

    Args:
        target_chars: Characters to probe.

    Returns:
        True if encodable; otherwise False.

    """
    encoding = sys.stdout.encoding or locale.getpreferredencoding(False)
    if not encoding:
        return False
    try:
        for ch in target_chars:
            ch.encode(encoding)
    except Exception:
        return False
    return True
