#!/bin/sh
# Fill print-plate color maps on an existing model library.
# Does not copy 3MF files, does not touch COS, nginx, auth, or env secrets.
# Default is a dry run. Set APPLY=1 to write, after a sqlite backup.
#
# Required:
#   FILAMENT_PICKER_MODELS_ROOT   private model directory (manifest.sqlite)
#   PLATE_EXTRACT_DIR             directory that contains models/<id>/meta.json
#   PLATE_BACKUP_DIR              directory for manifest backups
# Optional:
#   APPLY=1                       write plate_layout
#   RESTORE_BACKUP=/path/to.bak   restore that backup and exit
#   FILAMENT_PICKER_BIN           defaults to filament-picker on PATH
set -eu
BIN="${FILAMENT_PICKER_BIN:-filament-picker}"
: "${FILAMENT_PICKER_MODELS_ROOT:?set FILAMENT_PICKER_MODELS_ROOT}"
: "${PLATE_BACKUP_DIR:?set PLATE_BACKUP_DIR}"
if [ -n "${RESTORE_BACKUP:-}" ]; then
  exec "$BIN" models backfill-plates "${PLATE_EXTRACT_DIR:-.}" --restore "$RESTORE_BACKUP"
fi
: "${PLATE_EXTRACT_DIR:?set PLATE_EXTRACT_DIR to the extract that still has models/<id>/meta.json}"
if [ "${APPLY:-0}" = "1" ]; then
  exec "$BIN" models backfill-plates "$PLATE_EXTRACT_DIR" --backup-dir "$PLATE_BACKUP_DIR" --apply
fi
exec "$BIN" models backfill-plates "$PLATE_EXTRACT_DIR" --backup-dir "$PLATE_BACKUP_DIR"
