"""
boite_commercial.py — la boîte Gmail (Google Workspace) d'un commercial, connectée à Cheffer.

Demandé par Camille le 2026-10-26 : chaque commercial envoie ses campagnes depuis SA boîte,
connectée « par application ». Ce module est le socle (lot 1) : connecter, contrôler,
expliquer. L'envoi lui-même viendra au lot suivant, et il ne partira QUE si `envoi_possible`
est vrai ici.

## Trois décisions, prises avec Camille
1. **Mot de passe d'application**, pas OAuth. Le droit d'envoyer des emails est un accès
   « restreint » chez Google : une connexion OAuth exige une validation de l'application
   (des semaines, audit de sécurité annuel payant). Le mot de passe d'application marche
   aujourd'hui : SMTP pour envoyer, IMAP pour lire les réponses. Il est chiffré au repos
   (Fernet, même clé maître que les clés API des sites).
2. **Workspace sur un domaine à nous**, pas de @gmail.com. Sur un Gmail perso, SPF, DKIM et
   DMARC sont ceux de Google : les contrôler ne prouverait rien, et le démarchage depuis un
   compte perso fait suspendre le compte. Une adresse gmail.com est donc refusée.
3. **La chauffe est celle des autres boîtes** (`expediteur.plafond_chauffe`) : 14 jours sans
   AUCUN cold email, puis 15 par jour, +1 par jour, 35 au plus. Une adresse neuve qui
   démarche dès le premier jour, c'est le cas d'école du domaine grillé.

## « À chaque ouverture de session »
`etat(..., controler=True)` refait les contrôles : DNS du domaine ET connexion SMTP (un mot
de passe d'application révoqué côté Google ne se voit nulle part ailleurs). Le résultat est
gardé 10 minutes : une session qui s'ouvre trois fois de suite n'interroge pas trois fois
Google.
"""
from __future__ import annotations

import imaplib
import smtplib
import socket
from datetime import date, datetime, timezone

DOMAINES_PERSO = {"gmail.com", "googlemail.com"}
SMTP_HOTE, SMTP_PORT = "smtp.gmail.com", 587
IMAP_HOTE = "imap.gmail.com"
DELAI_CONTROLE_S = 600          # un contrôle de moins de 10 minutes est encore valable
TIMEOUT_S = 15

SCHEMA = """
CREATE TABLE IF NOT EXISTS boites_commerciales (
    utilisateur      text PRIMARY KEY,          -- le username Cheffer, la clé de tout
    site             text NOT NULL DEFAULT 'lcr',
    email            text,
    nom_affiche      text,
    mdp_chiffre      text,                      -- mot de passe d'application, Fernet
    connectee_le     timestamptz,               -- début de la chauffe
    smtp_ok          boolean,
    imap_ok          boolean,
    smtp_erreur      text,
    dns              jsonb,
    dns_bloquant     boolean,
    controle_le      timestamptz,
    accueil_vu_le    timestamptz,               -- l'explication de première connexion
    maj_le           timestamptz NOT NULL DEFAULT now()
);
"""

_TABLE_PRETE = False


def _pg():
    import pool_pg
    return pool_pg


def _assurer_table() -> None:
    global _TABLE_PRETE
    if not _TABLE_PRETE:
        _pg()._ecrire(SCHEMA)
        _TABLE_PRETE = True


def _ligne(utilisateur: str) -> dict | None:
    _assurer_table()
    cols = ("utilisateur", "site", "email", "nom_affiche", "mdp_chiffre", "connectee_le",
            "smtp_ok", "imap_ok", "smtp_erreur", "dns", "dns_bloquant", "controle_le",
            "accueil_vu_le")
    r = _pg()._q(f"SELECT {', '.join(cols)} FROM boites_commerciales WHERE utilisateur = %s",
                 (utilisateur,))
    return dict(zip(cols, r[0])) if r else None


# ── Les contrôles ─────────────────────────────────────────────────────────────
def _mdp_propre(mdp: str) -> str:
    # Google affiche le mot de passe en 4 blocs séparés d'espaces ; on le colle tel quel.
    return "".join((mdp or "").split())


def tester_smtp(email: str, mdp: str) -> tuple[bool, str]:
    try:
        with smtplib.SMTP(SMTP_HOTE, SMTP_PORT, timeout=TIMEOUT_S) as s:
            s.starttls()
            s.login(email, _mdp_propre(mdp))
        return True, ""
    except smtplib.SMTPAuthenticationError:
        return False, ("Google refuse ce mot de passe. Vérifie qu'il s'agit bien d'un mot de "
                       "passe d'APPLICATION (16 lettres), pas de ton mot de passe habituel.")
    except (socket.timeout, OSError) as e:
        return False, f"Serveur Gmail injoignable ({type(e).__name__}). Réessaie dans un instant."
    except Exception as e:  # noqa: BLE001
        return False, f"Connexion refusée : {str(e)[:160]}"


def tester_imap(email: str, mdp: str) -> tuple[bool, str]:
    try:
        m = imaplib.IMAP4_SSL(IMAP_HOTE, timeout=TIMEOUT_S)
        m.login(email, _mdp_propre(mdp))
        m.logout()
        return True, ""
    except Exception as e:  # noqa: BLE001
        return False, str(e)[:160]


def controler_dns(domaine: str) -> dict:
    """SPF, DKIM, DMARC — vus pour une boîte Google Workspace.

    `sante_envoi.controler_domaine` sait lire les trois enregistrements ; on y ajoute ce qui
    est propre à Google : le SPF doit inclure `_spf.google.com`, la clé DKIM doit être
    publiée sous le sélecteur `google`, les MX doivent pointer chez Google.
    """
    import sante_envoi as se
    r = se.controler_domaine(domaine)
    points = []

    spf = r.get("spf") or ""
    if not spf:
        points.append({"cle": "spf", "ok": False, "bloquant": True,
                       "titre": "SPF absent",
                       "detail": "Aucun serveur n'est autorisé à écrire au nom du domaine. "
                                 "Ajouter un TXT : v=spf1 include:_spf.google.com ~all"})
    elif "_spf.google.com" not in spf:
        points.append({"cle": "spf", "ok": False, "bloquant": True,
                       "titre": "SPF sans Google",
                       "detail": f"Le SPF existe mais n'autorise pas Gmail : « {spf} ». "
                                 "Il faut y ajouter include:_spf.google.com"})
    else:
        points.append({"cle": "spf", "ok": True, "titre": "SPF autorise Google", "detail": spf})

    import dns.resolver  # noqa: F401  (déjà requis par sante_envoi)
    cle_google = [x for x in se._txt(f"google._domainkey.{domaine}") if "p=" in x]
    if cle_google and len(cle_google[0].split("p=")[-1].strip()) > 40:
        points.append({"cle": "dkim", "ok": True, "titre": "DKIM Google publié",
                       "detail": "Clé trouvée sous le sélecteur « google »."})
    else:
        points.append({"cle": "dkim", "ok": False, "bloquant": True,
                       "titre": "DKIM Google introuvable",
                       "detail": "Les emails partiraient sans signature. Dans la console "
                                 "Google Admin : Applications › Gmail › Authentifier les "
                                 "e-mails, générer la clé puis publier le TXT "
                                 "google._domainkey."})

    dmarc = r.get("dmarc")
    if not dmarc:
        points.append({"cle": "dmarc", "ok": False, "bloquant": True, "titre": "DMARC absent",
                       "detail": "Gmail et Yahoo l'exigent depuis 2024 pour les expéditeurs "
                                 "réguliers. Ajouter un TXT _dmarc : "
                                 "v=DMARC1; p=none; rua=mailto:dmarc@" + domaine})
    else:
        pol = r.get("dmarc_politique") or ""
        points.append({"cle": "dmarc", "ok": True, "titre": f"DMARC présent (p={pol or '?'})",
                       "detail": dmarc,
                       "avertissement": ("Politique en observation seulement : suffisant pour "
                                         "envoyer, à durcir plus tard.") if pol == "none" else ""})

    mx = r.get("mx") or []
    if not any("google" in m.lower() for m in mx):
        points.append({"cle": "mx", "ok": False, "bloquant": False,
                       "titre": "MX hors Google",
                       "detail": "Les réponses n'arrivent pas dans Gmail : "
                                 + (", ".join(mx) or "aucun MX") + "."})
    else:
        points.append({"cle": "mx", "ok": True, "titre": "Les réponses arrivent dans Gmail",
                       "detail": ", ".join(mx)})

    return {"domaine": domaine, "points": points,
            "bloquant": any(p.get("bloquant") and not p["ok"] for p in points),
            "controle_le": datetime.now(timezone.utc).isoformat()}


# ── La chauffe ────────────────────────────────────────────────────────────────
def chauffe(connectee_le) -> dict:
    """Où en est la boîte, et ce qu'elle a le droit d'envoyer en cold aujourd'hui."""
    import expediteur as ex
    if not connectee_le:
        return {"jour": 0, "plafond_aujourdhui": 0, "phase": "non_connectee", "courbe": []}
    debut = connectee_le.date() if isinstance(connectee_le, datetime) else connectee_le
    aujourdhui = date.today()
    age = (aujourdhui - debut).days
    courbe = []
    for j in range(0, ex.CHAUFFE_JOURS + (ex.RAMPE_ARRIVEE - ex.RAMPE_DEPART) + 2):
        jour = date.fromordinal(debut.toordinal() + j)
        courbe.append({"jour": j + 1, "date": jour.isoformat(),
                       "plafond": ex.plafond_chauffe(debut, jour)})
    plafond = ex.plafond_chauffe(debut, aujourdhui)
    phase = ("chauffe" if age < ex.CHAUFFE_JOURS
             else "montee" if plafond < ex.RAMPE_ARRIVEE else "croisiere")
    return {"jour": age + 1, "plafond_aujourdhui": plafond, "phase": phase,
            "jours_avant_premier_cold": max(0, ex.CHAUFFE_JOURS - age),
            "plafond_max": ex.RAMPE_ARRIVEE, "courbe": courbe}


# ── Les gestes ────────────────────────────────────────────────────────────────
def connecter(utilisateur: str, site: str, email: str, mdp: str, nom_affiche: str = "") -> dict:
    email = (email or "").strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        return {"ok": False, "error": "Adresse email invalide."}
    domaine = email.split("@")[-1]
    if domaine in DOMAINES_PERSO:
        return {"ok": False, "error": "Les adresses @gmail.com ne sont pas acceptées : il faut "
                                      "ta boîte professionnelle Google Workspace "
                                      "(prenom@notre-domaine)."}
    if len(_mdp_propre(mdp)) != 16:
        return {"ok": False, "error": "Un mot de passe d'application fait 16 lettres. Copie-le "
                                      "tel que Google l'affiche."}

    smtp_ok, err = tester_smtp(email, mdp)
    if not smtp_ok:
        return {"ok": False, "error": err}
    imap_ok, _ = tester_imap(email, mdp)
    dns = controler_dns(domaine)

    import json
    import site_credentials_backend as scb
    _assurer_table()
    ancienne = _ligne(utilisateur)
    # La chauffe repart de zéro si l'ADRESSE change, pas si l'on reconnecte la même : un
    # mot de passe renouvelé ne rajeunit pas la boîte.
    garde_debut = bool(ancienne and ancienne.get("email") == email and ancienne.get("connectee_le"))
    _pg()._ecrire("""
        INSERT INTO boites_commerciales (utilisateur, site, email, nom_affiche, mdp_chiffre,
            connectee_le, smtp_ok, imap_ok, smtp_erreur, dns, dns_bloquant, controle_le, maj_le)
        VALUES (%s, %s, %s, %s, %s, now(), true, %s, NULL, %s, %s, now(), now())
        ON CONFLICT (utilisateur) DO UPDATE SET
            site = EXCLUDED.site, email = EXCLUDED.email, nom_affiche = EXCLUDED.nom_affiche,
            mdp_chiffre = EXCLUDED.mdp_chiffre,
            connectee_le = CASE WHEN %s THEN boites_commerciales.connectee_le ELSE now() END,
            smtp_ok = true, imap_ok = EXCLUDED.imap_ok, smtp_erreur = NULL,
            dns = EXCLUDED.dns, dns_bloquant = EXCLUDED.dns_bloquant,
            controle_le = now(), maj_le = now()
    """, (utilisateur, site, email, (nom_affiche or "").strip()[:80],
          scb.encrypt_value(_mdp_propre(mdp)), imap_ok, json.dumps(dns), dns["bloquant"],
          garde_debut))
    return {"ok": True, **etat(utilisateur)}


def deconnecter(utilisateur: str) -> dict:
    _assurer_table()
    # On efface le secret, pas l'historique : la date de connexion reste, pour qu'une
    # reconnexion de la même adresse ne fasse pas croire à une boîte neuve.
    _pg()._ecrire("UPDATE boites_commerciales SET mdp_chiffre = NULL, smtp_ok = false, "
                  "maj_le = now() WHERE utilisateur = %s", (utilisateur,))
    return {"ok": True, **etat(utilisateur)}


def accueil_vu(utilisateur: str, site: str) -> dict:
    _assurer_table()
    _pg()._ecrire("""
        INSERT INTO boites_commerciales (utilisateur, site, accueil_vu_le) VALUES (%s, %s, now())
        ON CONFLICT (utilisateur) DO UPDATE SET accueil_vu_le = now(), maj_le = now()
    """, (utilisateur, site))
    return {"ok": True}


def _recontroler(l: dict) -> dict:
    """Refait DNS + SMTP si le dernier contrôle a plus de 10 minutes. Rend la ligne à jour."""
    import json
    import site_credentials_backend as scb
    ctrl = l.get("controle_le")
    if ctrl and (datetime.now(timezone.utc) - ctrl).total_seconds() < DELAI_CONTROLE_S:
        return l
    mdp = scb.decrypt_value(l["mdp_chiffre"]) if l.get("mdp_chiffre") else None
    smtp_ok, err = tester_smtp(l["email"], mdp) if mdp else (False, "Mot de passe absent.")
    dns = controler_dns(l["email"].split("@")[-1])
    _pg()._ecrire("""
        UPDATE boites_commerciales SET smtp_ok = %s, smtp_erreur = %s, dns = %s,
               dns_bloquant = %s, controle_le = now(), maj_le = now()
        WHERE utilisateur = %s
    """, (smtp_ok, err or None, json.dumps(dns), dns["bloquant"], l["utilisateur"]))
    return _ligne(l["utilisateur"]) or l


def etat(utilisateur: str, controler: bool = False) -> dict:
    """Tout ce que l'écran et l'envoi doivent savoir. Le mot de passe ne sort jamais."""
    l = _ligne(utilisateur)
    if not l:
        return {"connectee": False, "accueil_vu": False, "envoi_possible": False,
                "raisons": ["Aucune boîte connectée."], "chauffe": chauffe(None)}
    connectee = bool(l.get("email") and l.get("mdp_chiffre"))
    if connectee and controler:
        l = _recontroler(l)
    ch = chauffe(l.get("connectee_le") if connectee else None)
    raisons = []
    if not connectee:
        raisons.append("Aucune boîte connectée.")
    else:
        if not l.get("smtp_ok"):
            raisons.append("Gmail refuse la connexion : " + (l.get("smtp_erreur") or "mot de passe à renouveler."))
        if l.get("dns_bloquant"):
            raisons.append("La configuration DNS du domaine est incomplète (SPF, DKIM ou DMARC).")
        if ch["plafond_aujourdhui"] == 0:
            raisons.append(f"Chauffe en cours : premier cold email dans "
                           f"{ch.get('jours_avant_premier_cold', 0)} jour(s).")
    return {
        "connectee": connectee, "email": l.get("email"), "nom_affiche": l.get("nom_affiche"),
        "smtp_ok": bool(l.get("smtp_ok")), "imap_ok": bool(l.get("imap_ok")),
        "smtp_erreur": l.get("smtp_erreur"), "dns": l.get("dns"),
        "dns_bloquant": bool(l.get("dns_bloquant")),
        "controle_le": l["controle_le"].isoformat() if l.get("controle_le") else None,
        "connectee_le": l["connectee_le"].isoformat() if l.get("connectee_le") else None,
        "accueil_vu": bool(l.get("accueil_vu_le")),
        "chauffe": ch, "envoi_possible": connectee and not raisons, "raisons": raisons,
    }
