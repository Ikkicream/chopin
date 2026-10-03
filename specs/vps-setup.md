# Setup VPS — Guide de déploiement

## Prérequis
- VPS : 204.168.186.159 (Ubuntu 24.04, 4GB RAM)
- SSH : `ssh -i ~/.ssh/id.mkdautoblog root@204.168.186.159`
- User app : autoblog (uid 1000)
- Claude Code déjà installé : `/usr/bin/claude` v2.1.81

## Étape 1 — Transfert des fichiers (depuis le Mac)
```bash
# Depuis le Mac local :
scp -i ~/.ssh/id.mkdautoblog -r /Users/camille/Genesis_kill_paperclips/ root@204.168.186.159:/home/autoblog/genesis/

# Fixer les permissions
ssh -i ~/.ssh/id.mkdautoblog root@204.168.186.159 "chown -R autoblog:autoblog /home/autoblog/genesis"
```

## Étape 2 — Configurer l'environnement sur le VPS
```bash
ssh -i ~/.ssh/id.mkdautoblog root@204.168.186.159
su - autoblog
cd /home/autoblog/genesis

# Copier le template et remplir les clés manquantes
cp .env.template .env
nano .env  # remplir DEEPSEEK_API_KEY, WP_USERNAME, WP_APP_PASSWORD...

# Créer les dossiers manquants
mkdir -p memory/{mkd,lcr,shared} skills dashboard/assets tools
```

## Étape 3 — Installer les outils
```bash
# claude-code-router (routage DeepSeek/Haiku/Sonnet)
npm install -g @musistudio/claude-code-router

# agent-flow (visualisation graph)
cd /home/autoblog/genesis/tools
git clone https://github.com/patoles/agent-flow
cd agent-flow && pnpm i

# agents-observe (observabilité)
# Via Claude Code marketplace (dans une session Claude Code)
# marketplace add simple10/agents-observe

# claude-usage (cost tracking)
cd /home/autoblog/genesis/tools
git clone https://github.com/phuryn/claude-usage

# Retour au projet
cd /home/autoblog/genesis
```

## Étape 4 — Lancer Claude Code dans tmux
```bash
su - autoblog
tmux new -s genesis
cd /home/autoblog/genesis

# Sourcer l'env
set -a; source .env; set +a

# Lancer avec le router (si DeepSeek configuré)
ccr code
# OU sans router :
claude

# Première chose à faire dans la session :
# 1. Lire @CLAUDE.md pour le contexte
# 2. Lire @specs/stack-tools.md pour l'ordre des tâches
# 3. Configurer les hooks (agent-flow setup)
# 4. Activer Remote Control : /remote
```

## Étape 5 — Activer Remote Control (contrôle depuis téléphone)
```
# Dans la session Claude Code :
/remote

# → URL + QR code affiché
# → Scanner avec l'app Claude sur iPhone
# → Tu peux maintenant envoyer des commandes depuis ton téléphone
```

## Étape 6 — Configurer Nginx pour les dashboards
```nginx
# Ajouter dans /etc/nginx/sites-available/genesis
server {
    listen 443 ssl;
    server_name genesis.mkdgroupe.dev;  # ou un sous-domaine

    ssl_certificate /etc/letsencrypt/live/genesis.mkdgroupe.dev/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/genesis.mkdgroupe.dev/privkey.pem;

    # Dashboard custom
    location / {
        root /home/autoblog/genesis/dashboard;
        index index.html;
    }

    # agent-flow
    location /agent-flow/ {
        proxy_pass http://127.0.0.1:3001/;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # agents-observe
    location /observe/ {
        proxy_pass http://127.0.0.1:4981/;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

## Étape 7 — Arrêter Paperclip (après validation)
```bash
# Seulement quand tout fonctionne sans Paperclip
su - autoblog
pm2 stop paperclip
pm2 save

# Garder les données en backup
cp -r /home/autoblog/.paperclip /home/autoblog/.paperclip.backup
```

## Se reconnecter à la session (depuis n'importe où)
```bash
# Depuis le Mac ou un autre terminal :
ssh -i ~/.ssh/id.mkdautoblog root@204.168.186.159
su - autoblog
tmux attach -t genesis
# → tu retrouves ta session Claude Code exactement où tu l'as laissée
```

## Commandes tmux utiles
```
Ctrl+B D        → détacher la session (elle continue en arrière-plan)
Ctrl+B [        → mode scroll (q pour quitter)
tmux ls         → lister les sessions
tmux kill-session -t genesis  → tuer la session
```
