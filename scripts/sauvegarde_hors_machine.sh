#!/usr/bin/env bash
# Sauvegarde hors machine — un instantané par jour, sans historique.
#
# POURQUOI CE SCRIPT EXISTE
# Le push de `backup.sh` échouait depuis le 2026-06-17 : GitHub Push Protection refusait
# tout envoi parce qu'une clé API était dans l'historique. 127 commits — deux mois et demi
# de travail — n'existaient que sur ce disque. Les ZIP de secours ? Sur le même disque.
# Et personne ne le savait : l'échec allait dans `backups/backup.log`, que personne ne lit.
#
# CE QUI CHANGE ICI
# On ne pousse pas l'HISTORIQUE, on pousse un ÉTAT : une branche orpheline d'un seul
# commit, remplacée chaque jour. Push Protection scanne ce qu'on envoie ; un arbre propre
# passe, même si le passé est bloqué. La sauvegarde n'attend donc plus le nettoyage.
#
# Et l'échec est BRUYANT : il écrit un drapeau que `alertes.py` regarde. Un avertissement
# que personne ne voit n'est pas un avertissement.
set -uo pipefail

RACINE="/home/autoblog/genesis"
BRANCHE="sauvegarde/courante"
DRAPEAU="$RACINE/memory/sauvegarde-echec.flag"
cd "$RACINE" || exit 1

DEPART="$(git rev-parse --abbrev-ref HEAD)"

# Le 2026-08-28, le `git checkout` de retour a été refusé et personne ne l'a vu : le dépôt
# est resté sur `$BRANCHE-tmp`, et les trois nuits suivantes ont échoué sur « une branche
# nommée ... existe déjà ». Deux conséquences qu'on ne veut plus jamais :
# `main` a cessé d'avancer, et les commits de `backup.sh` sont allés se perdre sur une
# branche orpheline que personne ne regardait.
# Donc : si on se réveille SUR la branche temporaire, on en sort ; et on efface le résidu
# avant de commencer, au lieu de buter dessus.
if [ "$DEPART" = "$BRANCHE-tmp" ]; then
  DEPART="main"
  git checkout -f -q "$DEPART" || { echo "[ÉCHEC] impossible de revenir sur $DEPART"; exit 1; }
fi
git branch -D "$BRANCHE-tmp" -q 2>/dev/null || true

echouer() {
  echo "[ÉCHEC] $1"
  printf '%s\n%s\n' "$(date -Is)" "$1" > "$DRAPEAU"
  git checkout -f -q "$DEPART" 2>/dev/null || true
  restaurer_non_suivis 2>/dev/null || true
  exit 1
}

# Un secret dans l'arbre ferait refuser le push par GitHub — autant le voir ICI, avec un
# message clair, plutôt que dans une trace distante que personne ne lira.
if git grep -qE 'sk_live_[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|xoxb-[A-Za-z0-9-]{20,}' -- . 2>/dev/null; then
  echouer "un secret est présent dans l'arbre suivi — le push serait refusé. Le retirer d'abord."
fi

# ⚠️ Les fichiers NON SUIVIS sur la branche de départ sont emportés par ce va-et-vient :
# ils entrent dans l'instantané, puis le retour sur la branche de travail les efface,
# puisqu'ils n'y existent pas. Ce script s'est supprimé lui-même de cette façon le
# 2026-08-27, dix minutes après sa création — récupéré depuis la sauvegarde qu'il venait
# de pousser, ce qui est au moins une preuve qu'elle marche.
# On les relève AVANT, on les remet APRÈS.
NON_SUIVIS="$(git ls-files --others --exclude-standard)"
if [ -n "$NON_SUIVIS" ]; then
  ABRI="$(mktemp -d)"
  echo "$NON_SUIVIS" | while IFS= read -r f; do
    [ -f "$f" ] || continue
    mkdir -p "$ABRI/$(dirname "$f")" && cp -p "$f" "$ABRI/$f"
  done
fi

restaurer_non_suivis() {
  [ -n "${ABRI:-}" ] && [ -d "$ABRI" ] || return 0
  (cd "$ABRI" && find . -type f -print0) | while IFS= read -r -d "" f; do
    dst="$RACINE/${f#./}"
    [ -e "$dst" ] || { mkdir -p "$(dirname "$dst")"; cp -p "$ABRI/${f#./}" "$dst"; }
  done
  rm -rf "$ABRI"
}

git checkout -q --orphan "$BRANCHE-tmp" || { restaurer_non_suivis; echouer "création de la branche impossible"; }
git rm -r --cached . -q >/dev/null 2>&1
git add -A >/dev/null 2>&1
git -c user.name="Genesis Bot" -c user.email="bot@leclientroi.com" \
    commit -q -m "sauvegarde: état au $(date +%Y-%m-%d\ %H:%M)" \
  || { git checkout -f -q "$DEPART"; git branch -D "$BRANCHE-tmp" -q 2>/dev/null; \
       echo "[OK] rien de neuf à sauvegarder"; rm -f "$DRAPEAU"; exit 0; }

# `--force` assumé : cette branche est un MIROIR de l'état du jour, pas un historique.
# Garder tous les instantanés ferait grossir le dépôt sans rien apporter — l'historique
# vit sur la branche de travail, celui-ci n'est qu'un filet.
if git push -q --force origin "$BRANCHE-tmp:$BRANCHE" 2>&1 | tail -5; then
  echo "[OK] sauvegarde poussée sur $BRANCHE"
  rm -f "$DRAPEAU"
else
  git checkout -f -q "$DEPART" 2>/dev/null
  git branch -D "$BRANCHE-tmp" -q 2>/dev/null
  echouer "git push refusé — jeton expiré, secret détecté, ou réseau."
fi

git checkout -f -q "$DEPART" || echouer "retour sur $DEPART impossible — le dépôt resterait sur $BRANCHE-tmp"
git branch -D "$BRANCHE-tmp" -q 2>/dev/null
restaurer_non_suivis

# Dernier mot : on vérifie qu'on est bien rentré. Sans ça, l'échec du 28/08 se rejouerait
# à l'identique — silencieux, et découvert trois jours plus tard.
ACTUELLE="$(git rev-parse --abbrev-ref HEAD)"
[ "$ACTUELLE" = "$DEPART" ] || echouer "le dépôt est resté sur $ACTUELLE au lieu de $DEPART"
exit 0
