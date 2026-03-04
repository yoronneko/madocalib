# Copyright (C) 2026 Cabinet Office, Japan, All rights reserved.
# Copyright (C) 2026 Lighthouse Technology & Consulting Co. Ltd., All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause
"""L6 pattern extractors (pure, UI-agnostic).

L6E: non-service channels (exclude 200/201).
L6D: service channels (only 200/201).
Return values are RTKLIB-style file patterns without a directory part.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List


def find_l6e_patterns(folder: str) -> List[str]:
    """List L6E patterns excluding 200/201.

    Args:
        folder: Directory containing *.l6 files.

    Returns:
        Sorted patterns like '%%Y%%n%%HU.<ddd>.l6'.

    """
    base = Path(folder or "")
    if not base.is_dir():
        return []

    # Collect only *.l6 files (case-insensitive).
    l6_files = [f for f in os.listdir(base) if f.lower().endswith(".l6")]
    if not l6_files:
        return []

    # Extract channel codes appearing at the very end: ".<ddd>.l6"
    re_chan = re.compile(r"\.(\d{3})\.l6$", re.IGNORECASE)
    channels = sorted({m.group(1) for f in l6_files if (m := re_chan.search(f))})

    # Exclude service channels for L6E (these belong to L6D).
    channels = [c for c in channels if c not in {"200", "201"}]

    # Compose RTKLIB patterns with date/time macros.
    return [f"%%Y%%n%%HU.{c}.l6" for c in channels]


def find_l6d_patterns(folder: str) -> List[str]:
    """List L6D patterns for 200/201 only.

    Args:
        folder: Directory containing *.l6 files.

    Returns:
        Patterns among ['%%Y%%n%%HU.200.l6', '%Y%n%HU.201.l6'].

    """
    base = Path(folder or "")
    if not base.is_dir():
        return []

    # Collect *.l6 files
    l6_files = [f for f in os.listdir(base) if f.lower().endswith(".l6")]
    if not l6_files:
        return []

    # Match only ".200.l6" or ".201.l6" (service channels)
    re_service = re.compile(r"\.(200|201)\.l6$", re.IGNORECASE)

    # We keep the full matched suffix ".200.l6" or ".201.l6" because
    suffixes = sorted({m.group(0) for f in l6_files if (m := re_service.search(f))})

    # Compose RTKLIB macro patterns
    return [f"%%Y%%n%%HU{suffix}" for suffix in suffixes]
