from pathlib import Path
from firmware_profile import require_profile
ROOT=Path(__file__).resolve().parents[2]
BACKUPS=ROOT/'outputs/backup'
OUT=ROOT/'outputs/firmware'
EXPECTED='__SOURCE_SHA__'
PROFILE = require_profile()
LOAD = PROFILE['load_address']
ENTRY = LOAD + PROFILE['patch_offset']
WINDOW_START, WINDOW_END=0x480000,0x5c0000
