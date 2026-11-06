#!/bin/bash
# Scrape IDF dept par dept — test fix DuckDB retry + fix basile seen_cities
SITE=lcr
SECTORS=immobilier
SCRIPT=/home/autoblog/genesis/scripts/autoscrape_backend.py
LOG_DIR=/home/autoblog/genesis/logs
DEPTS=(77 78 91 92 93 94 95)

echo "[idf-seq] Reprise depuis dept 77 — $(date)" | tee -a $LOG_DIR/idf_sequential.log

for DEPT in "${DEPTS[@]}"; do
    echo "[idf-seq] === Dept $DEPT — $(date) ===" | tee -a $LOG_DIR/idf_sequential.log
    python3 -u $SCRIPT --site $SITE --dept $DEPT --sectors $SECTORS --target-contacts 0 \
        >> $LOG_DIR/autoscrape-lcr-dept${DEPT}.log 2>&1
    EXIT=$?
    echo "[idf-seq] Dept $DEPT terminé (exit=$EXIT) — $(date)" | tee -a $LOG_DIR/idf_sequential.log
    sleep 5
done

echo "[idf-seq] TOUS LES DEPTS TERMINÉS — $(date)" | tee -a $LOG_DIR/idf_sequential.log
