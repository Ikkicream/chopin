#!/usr/bin/env bash
# Sauvegarde PostgreSQL — base `cheffer` (schémas mass_mailing, mmc_zylio, godmode, public).
#
# POURQUOI CE SCRIPT EXISTE (audit du 2026-11-23)
# `backup.sh` zippe les fichiers DuckDB et le code ; `sauvegarde_hors_machine.sh` pousse le
# code sur GitHub. PostgreSQL, lui, n'était sauvegardé NULLE PART : campagnes, envois,
# événements, comptes — tout ce que Cheffer a écrit depuis la migration n'existait qu'une
# fois, sur ce disque.
#
# CE QU'IL FAIT
#   1. pg_dump au format « custom » (compressé, restaurable table par table) ;
#   2. relit l'archive (pg_restore -l) avant de la déclarer bonne ;
#   3. garde 7 quotidiennes + 4 hebdomadaires (celle du dimanche) dans /var/backups/cheffer-pg
#      (dossier root, 700 : il y a des données personnelles dedans) ;
#   4. copie hors serveur si /etc/cheffer-sauvegarde-pg.conf définit DISTANT (voir plus bas).
#
# Lancé par /etc/cron.d/cheffer-sauvegarde-pg (root, 01:30 UTC — hors dispatch, avant le
# réentraînement de 02 h). Journal : /var/log/cheffer-sauvegarde-pg.log, surveillé par etat_technique.py
# (fraîcheur 26 h) et alertes.py : un échec finit par une ligne « SauvegardePgError: … »,
# la forme que le relevé reconnaît comme une exécution morte.
#
# Restaurer (base jetable, jamais par-dessus `cheffer` sans le décider) :
#   runuser -u postgres -- createdb cheffer_restaure
#   runuser -u postgres -- pg_restore -d cheffer_restaure --no-owner /var/backups/cheffer-pg/quotidien/cheffer-AAAA-MM-JJ.dump
set -uo pipefail

BASE="cheffer"
DEST="/var/backups/cheffer-pg"
GARDER_JOURS=7
GARDER_SEMAINES=4
CONF="/etc/cheffer-sauvegarde-pg.conf"
DATE="$(date -u +%Y-%m-%d)"

echouer() { echo "SauvegardePgError: $1"; exit 1; }
journal() { echo "[$(date -u +%FT%TZ)] $1"; }

[ "$(id -u)" = 0 ] || echouer "à lancer en root (pg_dump via l'utilisateur postgres)"

install -d -m 700 -o root -g root "$DEST" "$DEST/quotidien" "$DEST/hebdo"

FIN="$DEST/quotidien/${BASE}-${DATE}.dump"
TMP="$DEST/quotidien/.${BASE}-${DATE}.dump.part"
GLOB="$DEST/quotidien/globals-${DATE}.sql"

journal "début pg_dump $BASE"
DEBUT=$(date +%s)
# postgres écrit dans un fichier temporaire qu'il possède, root le récupère ensuite.
rm -f "$TMP"
nice -n 10 ionice -c3 runuser -u postgres -- pg_dump -Fc -Z 6 -d "$BASE" > "$TMP" \
  || { rm -f "$TMP"; echouer "pg_dump a échoué"; }

# Une archive qui ne se relit pas n'est pas une sauvegarde.
NB_TABLES=$(pg_restore -l "$TMP" 2>/dev/null | grep -c " TABLE DATA ")
NB_ATTENDU=$(runuser -u postgres -- psql -d "$BASE" -Atc \
  "SELECT count(*) FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema')")
if [ -z "$NB_TABLES" ] || [ "$NB_TABLES" -lt "$NB_ATTENDU" ]; then
  rm -f "$TMP"
  echouer "archive incomplète : $NB_TABLES tables lues, $NB_ATTENDU attendues"
fi
mv -f "$TMP" "$FIN"
chmod 600 "$FIN"

# Rôles et mots de passe (hachés) : sans eux, l'application ne se reconnecte pas après
# une restauration sur une machine neuve.
runuser -u postgres -- pg_dumpall --globals-only > "$GLOB" 2>/dev/null \
  || echouer "pg_dumpall --globals-only a échoué"
chmod 600 "$GLOB"

TAILLE=$(du -h "$FIN" | cut -f1)
journal "archive OK : $FIN ($TAILLE, $NB_TABLES tables, $(( $(date +%s) - DEBUT )) s)"

# Hebdomadaire : le dimanche, un lien dur (aucun octet de plus sur le disque).
if [ "$(date -u +%u)" = 7 ]; then
  ln -f "$FIN" "$DEST/hebdo/${BASE}-${DATE}.dump"
  ln -f "$GLOB" "$DEST/hebdo/globals-${DATE}.sql"
fi

# Rotation par NOMBRE (pas par âge : une panne de deux semaines ne doit pas tout effacer).
tourner() {  # dossier motif nombre
  ls -1t "$1"/$2 2>/dev/null | tail -n +"$(( $3 + 1 ))" | xargs -r rm -f
}
tourner "$DEST/quotidien" "${BASE}-*.dump" "$GARDER_JOURS"
tourner "$DEST/quotidien" "globals-*.sql" "$GARDER_JOURS"
tourner "$DEST/hebdo" "${BASE}-*.dump" "$GARDER_SEMAINES"
tourner "$DEST/hebdo" "globals-*.sql" "$GARDER_SEMAINES"

# --- Copie hors serveur ------------------------------------------------------------------
# /etc/cheffer-sauvegarde-pg.conf (root, 600) définit :
#   DISTANT="uXXXXXX-subN@uXXXXXX-subN.your-storagebox.de:cheffer-pg"   (destination rsync)
#   CLE="/root/.ssh/storagebox_cheffer"                                  (clé dédiée)
#   PORT=23
# Tant que ce fichier n'existe pas, les archives restent sur ce disque — et on le DIT.
if [ -f "$CONF" ]; then
  # shellcheck disable=SC1090
  . "$CONF"
  : "${DISTANT:?DISTANT absent de $CONF}" "${CLE:?CLE absente de $CONF}"
  PORT="${PORT:-23}"
  SSH="ssh -i $CLE -p $PORT -o BatchMode=yes -o ConnectTimeout=20"
  # Miroir exact du dossier local : la rotation locale s'applique aussi à distance.
  if rsync -a --delete --timeout=600 -e "$SSH" "$DEST/" "$DISTANT/" ; then
    # Contrôle côté distant : l'archive du jour est-elle là, et de la bonne taille ?
    LOCAL_O=$(stat -c%s "$FIN")
    DIST_O=$(rsync -e "$SSH" --list-only "$DISTANT/quotidien/$(basename "$FIN")" 2>/dev/null \
             | awk '{gsub(",","",$2); print $2}')
    [ "$DIST_O" = "$LOCAL_O" ] || echouer "copie distante incomplète ($DIST_O octets au lieu de $LOCAL_O)"
    journal "copie hors serveur OK → $DISTANT"
  else
    echouer "copie hors serveur impossible vers $DISTANT"
  fi
else
  journal "ATTENTION : copie hors serveur non configurée ($CONF absent) — archives sur ce disque seulement"
fi

journal "sauvegarde PostgreSQL terminée"
exit 0
