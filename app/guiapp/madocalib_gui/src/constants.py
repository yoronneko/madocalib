# Copyright (C) 2026 Cabinet Office, Japan, All rights reserved.
# Copyright (C) 2026 Lighthouse Technology & Consulting Co. Ltd., All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause
"""Constants shared across the application.

Notes:
    - Target platform: Windows.

"""
from typing import Final

# Executables/scripts (relative to the base directory returned by get_base_dir()).
PATH_BIN_RNX2RTKP: Final[str] = "bin/rnx2rtkp.exe"
PATH_BIN_RTKPLOT: Final[str] = "sample_data/rtkplot.exe"
PATH_BAT_RNX2RTKP: Final[str] = "bin/rnx2rtkp.bat"

# App config (relative to the base directory returned by get_base_dir()).
PATH_INI_MADOCALIBGUI: Final[str] = "bin/madocalib_gui.ini"
PATH_CONF_DEFAULT: Final[str] = "app/consapp/rnx2rtkp/gcc_mingw/sample.conf"
