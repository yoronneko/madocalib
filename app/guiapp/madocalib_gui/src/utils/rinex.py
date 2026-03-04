# Copyright (C) 2026 Cabinet Office, Japan, All rights reserved.
# Copyright (C) 2026 Lighthouse Technology & Consulting Co. Ltd., All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause
"""RINEX OBS utilities.

RINEX observation (OBS) parsing utilities.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import List


@dataclass(frozen=True)
class RinexSummary:
    """Minimal RINEX OBS summary.

    Attributes:
        version (float | None): RINEX version.
        ts (datetime | None): Start time.
        te (datetime | None): End time.
        interval (float | None): Sampling interval in seconds.

    """

    version: float | None
    ts: datetime | None
    te: datetime | None
    interval: float | None


def parse_rinex_obs(
    rnx_obs_path: str, tail_lines: int = 1000, chunk_size: int = 8192
) -> RinexSummary:
    """Parse a RINEX OBS file and return a minimal summary.

    Args:
        rnx_obs_path: RINEX OBS file path.
        tail_lines: Number of lines to read from the tail when inferring the
            last epoch.
        chunk_size: Chunk size in bytes used by the tail reader.

    Returns:
        RinexSummary: Parsed summary. If some fields cannot be parsed, the
        corresponding attributes are set to `None`.

    Notes:
        Used to pre-fill GUI date/time fields and the progress range.

    """
    rinex_version: float | None = None
    ts: datetime | None = None
    te: datetime | None = None
    interval: float | None = None
    header_ended = False
    first_epochs: List[datetime] = []

    def parse_epoch(line: str) -> datetime | None:
        """Parse a RINEX 3.x epoch line that starts with '>'."""
        if not line.startswith(">"):
            return None
        parts = line[1:].split()
        year, month, day, hour, minute = map(int, parts[:5])
        second = float(parts[5])
        sec_int = int(second)
        micro = int(round((second - sec_int) * 1_000_000))
        return datetime(year, month, day, hour, minute, sec_int, micro)

    def read_tail_lines(path: str, n_lines: int, chunk_size: int) -> list[str]:
        """Read the tail of a text file as a list of lines.

        Args:
            path: File path to read.
            n_lines: Max number of lines to collect from the end of the file.
            chunk_size: Block size in bytes for backward reads.

        Returns:
            The last lines reconstructed from the tail region. If the file does
            not exist or is empty, returns an empty list.

        Raises:
            OSError: If the file cannot be opened or read.

        """
        lines, leftover = [], b""
        with open(path, "rb") as fb:
            fb.seek(0, os.SEEK_END)
            pos = fb.tell()
            while pos > 0 and len(lines) < n_lines:
                size = min(chunk_size, pos)
                pos -= size
                fb.seek(pos)
                block = fb.read(size)
                data = block + leftover
                parts = data.split(b"\n")
                leftover = parts[0]
                for ln in parts[1:][::-1]:
                    lines.append(ln.decode(errors="ignore"))
                    if len(lines) >= n_lines:
                        break
            if leftover and len(lines) < n_lines:
                lines.append(leftover.decode(errors="ignore"))
        return list(reversed(lines))

    # Header + first epochs
    with open(rnx_obs_path, "r", errors="ignore") as f:
        for line in f:
            if not header_ended:
                if "RINEX VERSION" in line:
                    try:
                        rinex_version = float(line[:9].strip())
                    except Exception:
                        rinex_version = None
                elif "TIME OF FIRST OBS" in line:
                    parts = line[:43].split()
                    y, m, d, H, M, S = map(float, parts[:6])
                    ts = datetime(int(y), int(m), int(d), int(H), int(M), int(S))
                elif "TIME OF LAST OBS" in line:
                    parts = line[:43].split()
                    y, m, d, H, M, S = map(float, parts[:6])
                    te = datetime(int(y), int(m), int(d), int(H), int(M), int(S))
                elif "INTERVAL" in line:
                    try:
                        interval = float(line[:10].strip())
                    except Exception:
                        interval = None
                elif "END OF HEADER" in line:
                    header_ended = True
                    continue
            else:
                # RINEX 3.x epoch lines start with '>'
                if rinex_version and rinex_version >= 3.0:
                    ep = parse_epoch(line)
                    if ep:
                        ts = ts or ep
                        first_epochs.append(ep)
                        # Try to read the second epoch as well for interval derivation
                        while len(first_epochs) < 2:
                            nxt = next(f, None)
                            if not nxt:
                                break
                            ep2 = parse_epoch(nxt)
                            if ep2:
                                first_epochs.append(ep2)
                                break
                        break

    # Tail epoch (if not found in header)
    if te is None:
        for ln in reversed(read_tail_lines(rnx_obs_path, tail_lines, chunk_size)):
            ep = parse_epoch(ln)
            if ep:
                te = ep
                break

    # Interval from first two epochs if missing
    if interval is None and len(first_epochs) >= 2:
        interval = (first_epochs[1] - first_epochs[0]).total_seconds()

    return RinexSummary(version=rinex_version, ts=ts, te=te, interval=interval)
