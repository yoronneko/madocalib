# Copyright (C) 2026 Cabinet Office, Japan, All rights reserved.
# Copyright (C) 2026 Lighthouse Technology & Consulting Co. Ltd., All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause
"""INI-backed application settings.

Provides dataclasses for options/inputs/output/history and a service
to load/save them from/to an INI file.

"""

import configparser
import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

MAX_HISTORY = 10


@dataclass
class Options:
    """Run-time option fields bound to the main window.

    Attributes:
        start_date (str): Time Start (date part) in `YYYY/MM/DD`.
        start_time (str): Time Start (time part) in `HH:MM:SS`.
        end_date (str): Time End (date part) in `YYYY/MM/DD`.
        end_time (str): Time End (time part) in `HH:MM:SS`.
        interval (str): Processing interval seconds (string-form as stored in GUI).
        timespan (str): Optional time span seconds for interval mode.
        spanshift (str): Optional span shift seconds for interval mode.

    """

    start_date: str = ""
    start_time: str = ""
    end_date: str = ""
    end_time: str = ""
    interval: str = ""
    timespan: str = ""
    spanshift: str = ""


@dataclass
class InputPaths:
    """Input paths bound to file/folder comboboxes.

    Attributes:
        obs_path (str): RINEX OBS file path.
        nav_path (str): RINEX NAV file path.
        l6d_path (str): L6D folder path.
        l6e_path (str): L6E folder path.
        conf_path (str): Active configuration (`.conf`) path.

    """

    obs_path: str = ""
    nav_path: str = ""
    l6d_path: str = ""
    l6e_path: str = ""
    conf_path: str = ""


@dataclass
class OutputSettings:
    """Output destination and mode.

    Attributes:
        enabled_solution_folder (bool): `True` for Dir mode;
                                        `False` for single-file mode.
        folder_solution (str): Output directory when Dir mode is enabled.
        file_solution (str): Solution file path when single-file mode.

    """

    enabled_solution_folder: bool = False
    folder_solution: str = ""
    file_solution: str = ""


@dataclass
class HistorySettings:
    """Path histories shown in HistoryCombobox widgets (MRU order).

    Attributes:
        obs_histories (list[str]): OBS file history.
        nav_histories (list[str]): NAV file history.
        l6d_histories (list[str]): L6D folder history.
        l6e_histories (list[str]): L6E folder history.
        solution_folder_histories (list[str]): Output folder history.
        solution_file_histories (list[str]): Output file history.

    """

    obs_histories: List[str] = field(default_factory=list)
    nav_histories: List[str] = field(default_factory=list)
    l6d_histories: List[str] = field(default_factory=list)
    l6e_histories: List[str] = field(default_factory=list)
    solution_folder_histories: List[str] = field(default_factory=list)
    solution_file_histories: List[str] = field(default_factory=list)


@dataclass
class AppSettings:
    """Top-level settings container persisted to INI.

    Attributes:
        options (Options): Run-time options.
        inputs (InputPaths): Input file/folder paths.
        output (OutputSettings): Output destination and flags.
        history (HistorySettings): In-memory path histories.

    """

    options: Options = field(default_factory=Options)
    inputs: InputPaths = field(default_factory=InputPaths)
    output: OutputSettings = field(default_factory=OutputSettings)
    history: HistorySettings = field(default_factory=HistorySettings)


class SettingsService:
    """Service to load/save AppSettings from/to an INI file."""

    def __init__(self, ini_path: Path) -> None:
        """Create settings service bound to the specified INI path."""
        self.ini_path = ini_path
        self.data = AppSettings()

    def _load_history_settings(
        self, parser: configparser.ConfigParser
    ) -> HistorySettings:
        """Load path histories from INI with JSON-list fallback.

        Args:
            parser (ConfigParser): Parsed INI.

        Returns:
            HistorySettings: Normalized history lists (capped by `MAX_HISTORY`).

        """
        sec_hist = "History"
        hs = HistorySettings()

        def _load_list(key_hist: str, section: str, key_latest: str) -> list[str]:
            raw = parser.get(sec_hist, key_hist, fallback="")
            if raw:
                try:
                    arr = json.loads(raw)
                    if isinstance(arr, list):
                        return [str(x) for x in arr][:MAX_HISTORY]
                except Exception as e:
                    logger.warning("history load failed: %s: %s", key_hist, e)
            latest = parser.get(section, key_latest, fallback="").strip()
            return [latest] if latest else []

        hs.obs_histories = _load_list("obs_histories", "Input", "obs_path")
        hs.nav_histories = _load_list("nav_histories", "Input", "nav_path")
        hs.l6d_histories = _load_list("l6d_histories", "Input", "l6d_path")
        hs.l6e_histories = _load_list("l6e_histories", "Input", "l6e_path")
        hs.solution_folder_histories = _load_list(
            "solution_folder_histories", "Output", "folder_solution"
        )
        hs.solution_file_histories = _load_list(
            "solution_file_histories", "Output", "file_solution"
        )
        return hs

    def load(self) -> None:
        """Load settings from the INI file (encoding-tolerant)."""
        cfg = configparser.ConfigParser()
        if self.ini_path.exists():
            for enc in ("utf-8", "utf-8-sig", "cp932"):
                try:
                    cfg.read(self.ini_path, encoding=enc)
                    break
                except Exception:
                    continue

        def get(sec, key, default) -> str:
            return cfg.get(sec, key, fallback=str(default))

        # Options
        self.data.options = Options(
            start_date=get("Options", "start_date", self.data.options.start_date),
            start_time=get("Options", "start_time", self.data.options.start_time),
            end_date=get("Options", "end_date", self.data.options.end_date),
            end_time=get("Options", "end_time", self.data.options.end_time),
            interval=get("Options", "interval", self.data.options.interval),
            timespan=get("Options", "timespan", self.data.options.timespan),
            spanshift=get("Options", "spanshift", self.data.options.spanshift),
        )

        # Input
        self.data.inputs = InputPaths(
            obs_path=get("Input", "obs_path", ""),
            nav_path=get("Input", "nav_path", ""),
            l6d_path=get("Input", "l6d_path", ""),
            l6e_path=get("Input", "l6e_path", ""),
            conf_path=get("Input", "conf_path", ""),
        )

        # Output
        enable = get("Output", "enabled_solution_folder", "false").lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        self.data.output = OutputSettings(
            enabled_solution_folder=enable,
            folder_solution=get("Output", "folder_solution", ""),
            file_solution=get("Output", "file_solution", ""),
        )

        # History
        self.data.history = self._load_history_settings(cfg)

    def save(self) -> None:
        """Save settings to the INI file in UTF-8, including history lists."""
        cfg = configparser.ConfigParser()

        cfg["Options"] = {k: str(v) for k, v in asdict(self.data.options).items()}
        cfg["Input"] = {k: str(v) for k, v in asdict(self.data.inputs).items()}

        out = asdict(self.data.output).copy()
        out["enabled_solution_folder"] = (
            "true" if self.data.output.enabled_solution_folder else "false"
        )
        cfg["Output"] = {k: str(v) for k, v in out.items()}

        cfg["History"] = {}

        def _dump(name, arr) -> None:
            cfg["History"][name] = json.dumps(arr if arr else [""], ensure_ascii=False)

        _dump("obs_histories", self.data.history.obs_histories)
        _dump("nav_histories", self.data.history.nav_histories)
        _dump("l6d_histories", self.data.history.l6d_histories)
        _dump("l6e_histories", self.data.history.l6e_histories)
        _dump("solution_folder_histories", self.data.history.solution_folder_histories)
        _dump("solution_file_histories", self.data.history.solution_file_histories)

        with self.ini_path.open("w", encoding="utf-8") as f:
            cfg.write(f)
