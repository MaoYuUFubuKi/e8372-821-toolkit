from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BACKUPS=ROOT/'outputs/backup'
OUT=ROOT/'outputs/firmware'
EXPECTED='__SOURCE_SHA__'
LOAD, ENTRY=0x06882000,0x0690acfa
WINDOW_START, WINDOW_END=0x480000,0x5c0000
