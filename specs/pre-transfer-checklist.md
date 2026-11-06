# Checklist avant transfert & nettoyage VPS

## ANALYSE DE CONFLIT — RÉSULTAT : AUCUN ✅

### Ports occupés
| Port | Service | Conflit Genesis ? |
|---|---|---|
| 22 | SSH | Non |
| 80/443 | Nginx | Non — on ajoute un vhost, pas de conflit |
| 3000 | Twenty CRM (Docker) | Non — on ne touche pas |
| 3100 | Paperclip | Non — Genesis n'utilise pas ce port |
| 4321 | Emdash CMS (LCR) | Non — Genesis UTILISE emdash, pas de conflit |
| 5055 | lcr-webhook | Non |
| 54329 | PostgreSQL Paperclip | Non — Genesis n'a pas besoin de PG |

### Services à NE PAS TOUCHER
| Service | PM2 | Pourquoi |
|---|---|---|
| emdashcms | root, pid 2642908 | C'est le CMS de LCR — le site tombe sans |
| lcr-webhook | root, pid 2642907 | Webhook Tally → Twenty CRM |
| Twenty CRM | Docker (4 containers) | CRM — rien à voir avec Genesis |
| Nginx | system | Reverse proxy — on ajoute un vhost |

### Ce qu'on peut toucher
| Service | Action |
|---|---|
| paperclip (PM2 autoblog) | STOP après backup, puis DELETE |
| `/home/autoblog/.paperclip/` | SUPPRIMER après backup (sauf agents/) |
| `/home/autoblog/autoblog/` | GARDER en backup, ne pas toucher |

### Ressources VPS
| Ressource | Disponible | Genesis besoin |
|---|---|---|
| Disque | **51 GB libres** sur 75 GB | ~500 MB max |
| RAM | **5.3 GB dispo** sur 7.6 GB | ~200 MB (Claude Code + tools) |
| CPU | 4 cores, load 0.04 | Très léger |

**Verdict : on peut installer Genesis à côté de Paperclip sans aucun problème. Le VPS a largement la place.**

---

## PROCÉDURE COMPLÈTE (backup + transfert + setup)

### Étape 1 — Backup Paperclip sur le VPS (avant suppression)
```bash
ssh -i ~/.ssh/id.mkdautoblog root@204.168.186.159

# Créer le dossier Genesis + backup
mkdir -p /home/autoblog/genesis/backup

# 1. Articles LCR backlog (228 fichiers, 3MB) — CRITIQUE
cp -r /home/autoblog/blog/articles/ /home/autoblog/genesis/backup/lcr-articles/

# 2. Agents MKD complet (instructions + mémoire, sans node_modules)
rsync -av --exclude='node_modules' /home/autoblog/autoblog/agents/ /home/autoblog/genesis/backup/mkd-agents/

# 3. Agents LCR complet (instructions + mémoire + life)
cp -r /home/autoblog/.paperclip/instances/default/companies/56727614-8078-4d13-8595-38fd1e72496b/agents/ /home/autoblog/genesis/backup/lcr-agents/

# 4. Webhook tally-twenty
cp -r /home/autoblog/webhook/ /home/autoblog/genesis/backup/webhook/

# 5. Config .claude existante
cp /home/autoblog/autoblog/.claude/settings.json /home/autoblog/genesis/backup/claude-settings.json 2>/dev/null

# 6. Fixer les permissions
chown -R autoblog:autoblog /home/autoblog/genesis

# Vérifier
echo "=== BACKUP ==="
du -sh /home/autoblog/genesis/backup/*/
```

### Étape 2 — Transférer Genesis depuis le Mac
```bash
# Depuis le Mac :
scp -i ~/.ssh/id.mkdautoblog -r /Users/camille/Genesis_kill_paperclips/* root@204.168.186.159:/home/autoblog/genesis/
scp -i ~/.ssh/id.mkdautoblog /Users/camille/Genesis_kill_paperclips/.env.template root@204.168.186.159:/home/autoblog/genesis/

# Fixer permissions
ssh -i ~/.ssh/id.mkdautoblog root@204.168.186.159 "chown -R autoblog:autoblog /home/autoblog/genesis"
```

### Étape 3 — Configurer .env sur le VPS
```bash
ssh -i ~/.ssh/id.mkdautoblog root@204.168.186.159
su - autoblog
cd /home/autoblog/genesis
cp .env.template .env
# Vérifier que toutes les clés sont bonnes
```

### Étape 4 — Stop Paperclip (quand tout est validé)
```bash
su - autoblog
pm2 stop paperclip
pm2 delete paperclip
pm2 save
```

### Étape 5 — Nettoyage (APRÈS validation)
```bash
# Supprimer les données Paperclip volumineuses (500MB+ de logs)
rm -rf /home/autoblog/.paperclip/instances/default/data/run-logs/
rm -rf /home/autoblog/.paperclip/instances/default/data/backups/
rm -rf /home/autoblog/.paperclip/instances/default/logs/
rm -rf /home/autoblog/.paperclip/instances/default/db/

# Garder le reste en archive (léger)
# On pourra supprimer /home/autoblog/.paperclip/ complètement plus tard
```

---

## PAGE MONITORING — Health Check & Crédits

### Fonctionnalités
- ✅/❌ Status de chaque connexion (API Anthropic, DeepSeek, Emdash, WordPress, Telegram)
- 💰 Crédits restants Anthropic + DeepSeek (refresh quotidien)
- 📊 Consommation des dernières 24h / 7 jours / 30 jours
- 🔔 Alerte Telegram si un service tombe ou si crédit < seuil

### Tech
- Script bash/python exécuté par cron toutes les heures
- Génère un fichier JSON `health.json`
- Page HTML statique qui lit le JSON
- Servie par Nginx sur genesis.mkdgroupe.dev/health

### Checks à effectuer
```
1. Anthropic API    → GET https://api.anthropic.com/v1/messages (test minimal)
                    → GET /v1/organizations/usage (crédits restants)
2. DeepSeek API     → GET https://api.deepseek.com/user/balance
3. Emdash CMS      → GET http://localhost:4321/_emdash/api/content/posts?limit=1
4. WordPress MKD   → GET https://mkdgroupe.com/wp-json/wp/v2/posts?per_page=1
5. Telegram Bot     → GET https://api.telegram.org/bot{TOKEN}/getMe
6. Twenty CRM      → GET http://localhost:3000/healthcheck
7. Nginx           → curl -s http://localhost
8. Disk space      → df -h /
9. RAM             → free -h
10. PM2 processes  → pm2 jlist
```

### Format health.json
```json
{
  "lastCheck": "2026-05-01T08:00:00Z",
  "services": {
    "anthropic": { "status": "ok", "credits_usd": 18.45, "latency_ms": 230 },
    "deepseek": { "status": "ok", "credits_usd": 9.80, "latency_ms": 180 },
    "emdash": { "status": "ok", "latency_ms": 12 },
    "wordpress": { "status": "ok", "latency_ms": 340 },
    "telegram": { "status": "ok", "bot_name": "Leclientroibot" },
    "twenty": { "status": "ok", "latency_ms": 45 },
    "nginx": { "status": "ok" }
  },
  "system": {
    "disk_used_pct": 31,
    "ram_used_pct": 30,
    "pm2_processes": 3
  },
  "alerts": []
}
```

### Alerte automatique Telegram si :
- Un service passe en `"status": "error"`
- Crédits Anthropic < $5
- Crédits DeepSeek < $2
- Disque > 80%
- RAM > 90%
