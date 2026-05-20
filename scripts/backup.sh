#!/bin/bash
# Genesis — Backup automatique quotidien
# Usage: cron chaque soir 23h → git push + ZIP daté
# Emplacement: /home/autoblog/genesis/scripts/backup.sh

set -e

GENESIS_DIR="/home/autoblog/genesis"
BACKUP_DIR="/home/autoblog/genesis/backups"
DATE=$(date +%Y-%m-%d)
VERSION=$(date +%H%M)

cd "$GENESIS_DIR"

# === 1. Git commit & push ===
if [ -d ".git" ]; then
  git add -A
  git diff --cached --quiet || {
    git commit -m "auto: backup quotidien $DATE" --author="Genesis Bot <bot@genesis.local>"
    PUSH_OUT=$(GIT_TERMINAL_PROMPT=0 git push origin main 2>&1) || {
      echo "[WARN] git push failed:"
      echo "$PUSH_OUT" | sed 's/^/  /'
      echo "  → Fix: configurer un PAT GitHub avec credential.helper store ou remote URL avec token"
    }
  }
else
  echo "[WARN] No .git directory — skipping git backup"
fi

# === 2. ZIP archive ===
mkdir -p "$BACKUP_DIR"
ZIP_NAME="genesis-${DATE}-v${VERSION}.zip"

zip -r "$BACKUP_DIR/$ZIP_NAME" . \
  -x "*.git/*" \
  -x "node_modules/*" \
  -x "tools/*" \
  -x "__pycache__/*" \
  -x "backups/*" \
  -x ".env" \
  -x "*.pyc" \
  > /dev/null 2>&1

echo "[OK] Backup: $BACKUP_DIR/$ZIP_NAME"

# === 3. Rotation — garder les 30 derniers ZIPs ===
cd "$BACKUP_DIR"
ls -t genesis-*.zip 2>/dev/null | tail -n +31 | xargs rm -f 2>/dev/null

echo "[OK] Backup terminé — $(date)"
