// pm2 ecosystem config — Genesis Swarm
// Démarrer: pm2 start scripts/ecosystem.config.js
// Voir: pm2 list
// Logs: pm2 logs genesis-briefing

module.exports = {
  apps: [
    {
      // Briefing quotidien 7h UTC
      name: 'genesis-briefing',
      script: '/home/autoblog/genesis/scripts/orchestrator.py',
      interpreter: 'python3',
      args: '--task briefing',
      cron_restart: '0 7 * * *',   // Chaque jour à 7h00 UTC
      autorestart: false,
      watch: false,
      env: {
        PYTHONPATH: '/home/autoblog/genesis',
      },
    },
    {
      // Sync CRM lun-ven 8h UTC
      name: 'genesis-crm-sync',
      script: '/home/autoblog/genesis/scripts/orchestrator.py',
      interpreter: 'python3',
      args: '--task crm-sync',
      cron_restart: '0 8 * * 1-5',  // Lun-Ven à 8h00 UTC
      autorestart: false,
      watch: false,
    },
    {
      // Statut campagnes lundi 9h UTC
      name: 'genesis-campaign-status',
      script: '/home/autoblog/genesis/scripts/orchestrator.py',
      interpreter: 'python3',
      args: '--task campaign-status',
      cron_restart: '0 9 * * 1',    // Lundi à 9h00 UTC
      autorestart: false,
      watch: false,
    },
  ],
};
