# Emelia — LinkedIn Automation

## Ce qu'Emelia fait sur LinkedIn (remplace Zernio)

### Actions automatisables
1. **Visite de profil** — notifier le prospect que tu as vu son profil
2. **Demande de connexion** — avec ou sans note personnalisée
3. **Message** — envoyer un message direct (après connexion)
4. **Séquences** — enchaîner les actions avec délais

### Sécurité
- 100% cloud (pas d'extension navigateur = pas de risque de ban LinkedIn)
- Simulation de comportement humain
- Limites quotidiennes respectées automatiquement

### Format des steps LinkedIn
```json
{
  "steps": [
    {"type": "visit_profile", "delay": {"amount": 0, "unit": "MINUTES"}},
    {"type": "connection_request", "delay": {"amount": 2, "unit": "DAYS"}, "note": "Message de connexion"},
    {"type": "message", "delay": {"amount": 1, "unit": "DAYS"}, "message": "Contenu du message"}
  ]
}
```

### Campagnes Avancées (Multicanal)
Le vrai power : combiner email + LinkedIn dans un seul workflow :
1. **Email J+0** → si pas d'ouverture après 3 jours →
2. **Visite profil LinkedIn J+3** →
3. **Demande de connexion J+4** →
4. **Message LinkedIn J+6** (si connexion acceptée)
5. **Email relance J+7** (si toujours pas de réponse)

### Usage pour Genesis
- **LCR** : prospecter les PME locales (commerçants, restaurants, artisans)
- **MKD** : prospecter les DPO, responsables data, DSI
- Le tout piloté par l'agent `swarm-outreach`
