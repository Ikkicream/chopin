#!/usr/bin/env python3
"""BAT de test du tracking de clic Sweego → webhook Genesis → lead /acquisition.
Lancé MANUELLEMENT par Camille (envoi réel à sa propre adresse).
Usage : sudo -u autoblog python3 scripts/send_bat_test.py
"""
import sys
sys.path.insert(0, "/home/autoblog/genesis/scripts")
import sweego_backend as sw

html = """<html><body>
<p>Bonjour Camille,</p>
<p>BAT de test du tracking de clic Genesis &times; Sweego.</p>
<p><b>Clique ce lien pour valider :</b>
   <a href="https://leclientroi.com">Voir le site Le Client Roi</a></p>
<p>Apr&egrave;s le clic, tu dois appara&icirc;tre en lead dans /site/lcr/acquisition.</p>
</body></html>"""

res = sw.send_campaign(
    campaign_id="lcr-bat-webhook-test",
    subject="Test tracking Genesis (clic)",
    html_str=html,
    recipients=["camille@leclientroi.com"],
    dry_run=False,
    utm_campaign="lcr-bat-webhook-test",
)
print(res)
