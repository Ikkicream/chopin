#!/bin/bash
# Genesis — Backup automatique quotidien
# Usage: cron chaque soir 23h → git push + ZIP daté
# Emplacement: /home/autoblog/genesis/scripts/backup.sh

# set -e retiré 2026-05-23 — git push fail ne doit pas arrêter le backup

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

# === 2b. Frontend genesis-ui (dossier FRÈRE de genesis) — source only ===
# Sans ça, toute l'UI (Next.js/shadcn) n'était jamais sauvegardée. node_modules/.next exclus (régénérables).
UI_DIR="/home/autoblog/genesis-ui"
if [ -d "$UI_DIR" ]; then
  ( cd "$(dirname "$UI_DIR")" && zip -r "$BACKUP_DIR/$ZIP_NAME" "$(basename "$UI_DIR")" \
      -x "*/node_modules/*" \
      -x "*/.next/*" \
      -x "*/.turbo/*" \
      -x "*/.pnpm-store/*" \
      > /dev/null 2>&1 )
  echo "[OK] Frontend genesis-ui ajouté au ZIP (sans node_modules/.next)"
else
  echo "[WARN] genesis-ui introuvable — frontend non sauvegardé"
fi

# === 3. Génération du changelog .log humain (avec DeepSeek si dispo) ===
LOG_NAME="genesis-${DATE}-v${VERSION}.log"
# Source .env pour DEEPSEEK_API_KEY
if [ -f "$GENESIS_DIR/.env" ]; then
  set -a
  source "$GENESIS_DIR/.env"
  set +a
fi
python3 "$GENESIS_DIR/scripts/generate_changelog.py" "$BACKUP_DIR/$LOG_NAME" 2>&1 || echo "[WARN] changelog generation failed"

# === 4. Rotation — garder les 3 derniers ZIPs et 3 derniers LOGs ===
cd "$BACKUP_DIR"
ls -t genesis-*.zip 2>/dev/null | tail -n +4 | xargs rm -f 2>/dev/null
ls -t genesis-*.log 2>/dev/null | tail -n +4 | xargs rm -f 2>/dev/null

# === BACKUP_V2_2026-05-22 : check fichiers critiques pool + master key ===
# NB : on est dans $BACKUP_DIR ici (cd plus haut) → on utilise des chemins absolus.
echo "[CHECK] Fichiers critiques inclus dans le ZIP :"
for f in data/contacts.duckdb data/god_mode.duckdb data/auth.duckdb data/.master_key; do
  if [ -f "$GENESIS_DIR/$f" ]; then
    SIZE=$(stat -c%s "$GENESIS_DIR/$f" 2>/dev/null || echo "?")
    echo "  ✓ $f ($SIZE bytes)"
  else
    echo "  ⚠ $f MANQUANT"
  fi
done

# Backup spécifique master_key (copie chiffrée à part pour disaster recovery)
if [ -f "$GENESIS_DIR/data/.master_key" ]; then
  cp -p "$GENESIS_DIR/data/.master_key" "$BACKUP_DIR/.master_key.bak"
  echo "[OK] Master key backed up to $BACKUP_DIR/.master_key.bak"
fi

echo "[OK] Backup terminé — $(date)"
