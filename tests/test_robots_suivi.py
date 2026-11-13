#!/usr/bin/env python3
"""Une ouverture ou un clic Cheffer : personne ou robot ? (scripts/robots_suivi.py, 21/10/2026).
Cas réels observés sur Zylio (Resend) et Cheffer (Maildoso) en octobre 2026."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from robots_suivi import APPLE, HUMAIN, INCERTAIN, ROBOT, classer  # noqa: E402

ECHECS = []
CHROME42 = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/42.0.2311.135 Safari/537.36 Edge/12.246"
PROXY = "Mozilla/5.0 (Windows NT 5.1; rv:11.0) Gecko Firefox/11.0 (via ggpht.com GoogleImageProxy)"
WIN = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36"
IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15"

CAS = [
    ("scanner Gmail : IP Google, Chrome/42, 3 s", "open", "66.249.91.10", CHROME42, 3, "GOOGLE", ROBOT),
    ("scanner Gmail même tardif", "open", "74.125.218.4", CHROME42, 900, "GOOGLE", ROBOT),
    ("personne sur Gmail : proxy d'images, 2 h après", "open", "66.249.84.3", PROXY, 7200, "GOOGLE", HUMAIN),
    ("Outlook bureau", "open", "85.31.168.2", "Mozilla/4.0 (compatible; ms-office; MSOffice 16)", 446, "", HUMAIN),
    ("box Orange, 20 min", "open", "90.24.105.1", WIN, 1200, "FR-ORANGE France Telecom", HUMAIN),
    ("antivirus Microsoft 365", "open", "4.251.36.12", WIN, 19, "MSFT Microsoft Corporation", ROBOT),
    ("préchargement Apple Mail", "open", "2a04:4e41::1", "Mozilla/5.0", 9537, "CLOUDFLAREWARP Cloudflare", APPLE),
    ("ancienne donnée : ni IP ni délai", "open", "", "", None, "", INCERTAIN),
    ("antivirus qui clique tout (Microsoft, 30 s)", "click", "4.251.36.20", WIN, 30, "MSFT Microsoft Corporation", ROBOT),
    ("clic en 20 s depuis une box", "click", "90.24.1.1", WIN, 20, "FR-ORANGE", ROBOT),
    ("vrai clic depuis un iPhone, 8 min", "click", "2001:861::1", IPHONE, 468, "FR-PROXAD Free SAS", HUMAIN),
    ("vrai clic, réseau inconnu, 1 h", "click", "81.2.3.4", WIN, 3600, "", HUMAIN),
    ("clic sans aucune information", "click", "", "", None, "", INCERTAIN),
    # Revue du 21/10 (n°5)
    ("robot qui se dit navigateur : curl depuis un hébergeur hors liste", "click", "5.6.7.8", "curl/8.4.0", 3600, "NETCUP GmbH", ROBOT),
    ("Chrome sans tête", "click", "5.6.7.8", "Mozilla/5.0 HeadlessChrome/120", 3600, "", ROBOT),
    ("passerelle Proofpoint qui clique tard", "click", "148.163.1.1", WIN, 5400, "PROOFPOINT-ASN", ROBOT),
    ("relais privé iCloud : Safari iPhone via Cloudflare, 10 min", "click", "172.225.1.1", IPHONE, 600, "CLOUDFLARENET Cloudflare", INCERTAIN),
    ("clic depuis un réseau nommé « cloud », 8 min (cas réel 22/10)", "click", "1.2.3.4", WIN, 480, "cloud", ROBOT),
    ("clic depuis CIE-US-NAT, 5 min (cas réel 22/10)", "click", "1.2.3.5", WIN, 300, "CIE-US-NAT", ROBOT),
    ("fausse signature Gmail depuis un serveur Hetzner", "open", "2a01:4f9::1", PROXY, 600, "DE-HETZNER Hetzner Online GmbH", ROBOT),
    ("ouverture tardive depuis une IP Microsoft : on ne tranche pas", "open", "52.1.1.1", WIN, 7200, "MSFT Microsoft Corporation", INCERTAIN),
]
for nom, kind, ip, ua, sec, org, attendu in CAS:
    v, raison = classer(kind, ip, ua, sec, org)
    ok = v == attendu
    print(f"  {'OK  ' if ok else 'ÉCHEC'}  {nom} → {v} ({raison})")
    if not ok:
        ECHECS.append(nom)
print("\n" + (f"{len(ECHECS)} ÉCHEC(S)" if ECHECS else "Tout est vert."))
sys.exit(1 if ECHECS else 0)
