#!/usr/bin/env python3
"""sante_envoi.py — la surveillance quotidienne de la délivrabilité.

Une adresse expéditrice ne meurt pas d'un coup : elle se dégrade. L'enregistrement DNS
qu'un hébergeur réécrit sans prévenir, le domaine qui entre dans une liste noire, le taux
d'ouverture qui s'effondre parce que les messages arrivent en indésirables — chacun de ces
signaux précède l'arrêt complet de plusieurs semaines, et chacun est invisible depuis
l'écran des campagnes, où tout continue d'afficher « envoyé ».

Le module regarde donc à trois endroits, du plus lent au plus rapide à se dégrader :

1. **La forme** — MX, SPF, DKIM, DMARC. Ce qui autorise techniquement le domaine à
   écrire. Une régression ici est brutale et totale : plus rien n'arrive.
2. **La réputation** — présence du serveur d'envoi dans les listes noires publiques.
3. **Le fond** — taux d'ouverture, de rebond, de plainte. Ce qui dit si les messages sont
   lus ou rangés en indésirables, bien avant qu'un fournisseur ne bloque quoi que ce soit.

Les seuils sont ceux des fournisseurs, pas des chiffres ronds :
  - **ouverture sous 5 %** : demande de Camille, et cohérent — sous ce niveau, le message
    n'est plus lu, il est classé ;
  - **rebond au-dessus de 3 %** : Google et Microsoft commencent à filtrer vers 5 %, on
    alerte avant ;
  - **plainte au-dessus de 0,1 %** : le seuil de Google Postmaster est à 0,3 %, mais il
    se franchit en une journée — à 0,1 % on a encore le temps de couper.

Chaque contrôle exige un VOLUME MINIMUM avant de conclure : deux rebonds sur trois envois
ne veulent rien dire, et une alerte qui crie pour rien finit par ne plus être lue.

Usage :
    python3 scripts/sante_envoi.py            # bilan complet, lisible
    python3 scripts/sante_envoi.py --json
"""
from __future__ import annotations

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Sélecteurs DKIM connus, testés dans cet ordre. `selector1` est celui de Maildoso sur
# leclient-roi.com ; les autres couvrent les hébergeurs courants, pour qu'un changement de
# fournisseur ne fasse pas crier l'alerte à tort.
SELECTEURS_DKIM = ("selector1", "selector2", "default", "mail", "dkim", "s1", "s2",
                   "google", "k1", "maildoso", "smtp", "em")

# Listes noires publiques interrogées. Volontairement courtes et consensuelles : une liste
# agressive produit des faux positifs, et une alerte fausse est pire qu'aucune alerte.
LISTES_NOIRES = ("zen.spamhaus.org", "bl.spamcop.net", "b.barracudacentral.org")

SEUIL_OUVERTURE = 5.0        # %  — plancher absolu : sous ce niveau, on n'est plus lu
# Un plancher absolu ne suffit pas. Le taux d'ouverture est à 54 % sur trente jours : le
# jour où il tombe à 20 %, quelque chose est cassé — et l'alerte à 5 % ne dirait toujours
# rien. C'est la CHUTE qui prévient à temps, pas le niveau.
CHUTE_OUVERTURE = 0.35       # perte d'un tiers par rapport à la référence
FENETRE_REFERENCE = 30       # jours de référence
SEUIL_REBOND = 3.0           # %
SEUIL_PLAINTE = 0.1          # %
VOLUME_MINIMUM = 50          # envois avant de tirer une conclusion
FENETRE_JOURS = 7


# ── 1. La forme : ce qui autorise le domaine à écrire ─────────────────────────
def _txt(nom: str) -> list[str]:
    import dns.resolver
    try:
        return [b"".join(r.strings).decode(errors="replace")
                for r in dns.resolver.resolve(nom, "TXT")]
    except Exception:
        return []


def controler_domaine(domaine: str) -> dict:
    """MX, SPF, DKIM, DMARC d'un domaine expéditeur."""
    import dns.resolver
    r: dict = {"domaine": domaine, "problemes": [], "avertissements": []}

    try:
        r["mx"] = sorted(str(x.exchange).rstrip(".") for x in dns.resolver.resolve(domaine, "MX"))
    except Exception as e:  # noqa: BLE001
        r["mx"] = []
        r["problemes"].append(f"aucun MX résolu ({type(e).__name__})")

    spf = [x for x in _txt(domaine) if x.lower().startswith("v=spf1")]
    r["spf"] = spf[0] if spf else None
    if not spf:
        r["problemes"].append("SPF absent — les serveurs destinataires n'ont aucune "
                              "autorisation à vérifier")
    elif len(spf) > 1:
        r["problemes"].append(f"{len(spf)} enregistrements SPF — un seul est autorisé, "
                              f"la vérification échoue quand il y en a plusieurs")
    else:
        if "+all" in spf[0]:
            r["problemes"].append("SPF en « +all » : n'importe qui peut écrire au nom du "
                                  "domaine")
        elif not ("-all" in spf[0] or "~all" in spf[0]):
            r["avertissements"].append("SPF sans « -all » ni « ~all » : aucune consigne "
                                       "pour les envois non autorisés")

    r["dkim"] = None
    for sel in SELECTEURS_DKIM:
        v = [x for x in _txt(f"{sel}._domainkey.{domaine}") if "p=" in x]
        if v:
            r["dkim"] = {"selecteur": sel, "cle_presente": "p=" in v[0] and
                         len(v[0].split("p=")[-1].strip()) > 40}
            if not r["dkim"]["cle_presente"]:
                r["problemes"].append(f"DKIM « {sel} » présent mais sans clé publique "
                                      f"exploitable (révocation ?)")
            break
    if r["dkim"] is None:
        r["problemes"].append("DKIM introuvable sur tous les sélecteurs connus — les "
                              "messages partent sans signature")

    dmarc = [x for x in _txt(f"_dmarc.{domaine}") if x.lower().startswith("v=dmarc1")]
    r["dmarc"] = dmarc[0] if dmarc else None
    if not dmarc:
        r["problemes"].append("DMARC absent")
    else:
        politique = ""
        for morceau in dmarc[0].split(";"):
            if morceau.strip().lower().startswith("p="):
                politique = morceau.split("=", 1)[1].strip().lower()
        r["dmarc_politique"] = politique
        if politique == "none":
            r["avertissements"].append("DMARC en « p=none » : la politique n'est pas "
                                       "appliquée, elle est seulement observée")
    return r


# ── 2. La réputation : les listes noires ──────────────────────────────────────
def _ips(hote: str) -> list[str]:
    import dns.resolver
    try:
        return sorted(x.address for x in dns.resolver.resolve(hote, "A"))
    except Exception:
        return []


def controler_listes_noires(hote: str) -> dict:
    """Le serveur d'envoi figure-t-il dans une liste noire publique ?

    **Le code de retour fait tout.** Une liste DNSBL répond par une adresse en 127.0.0.x
    dont le dernier octet dit POURQUOI l'adresse est listée (2 à 11 chez Spamhaus). Mais
    elle répond AUSSI quand elle refuse la question — en 127.255.255.x — ce qui arrive
    systématiquement depuis un résolveur public ou trop bavard. Traiter toute réponse
    comme une inscription, c'est déclarer le monde entier en liste noire : le premier jet
    de ce module l'a fait, et annonçait dix serveurs bloqués alors qu'aucun ne l'était —
    `8.8.8.8` répondait pareil.

    On distingue donc trois issues : inscrit, non inscrit, et **contrôle impossible** —
    cette dernière ne doit pas déclencher d'alerte de blocage, seulement dire qu'on ne
    sait pas.
    """
    import dns.resolver
    r: dict = {"hote": hote, "ips": _ips(hote), "inscrit_dans": [],
               "non_verifiables": [], "problemes": []}
    if not r["ips"]:
        r["problemes"].append(f"impossible de résoudre {hote} — contrôle des listes "
                              f"noires impossible")
        return r
    for ip in r["ips"]:
        inverse = ".".join(reversed(ip.split(".")))
        for liste in LISTES_NOIRES:
            try:
                reponses = [x.address for x in
                            dns.resolver.resolve(f"{inverse}.{liste}", "A")]
            except Exception:
                continue          # pas de réponse = pas inscrit, c'est le cas normal
            vraies = [x for x in reponses if x.startswith("127.0.0.")
                      and x.rsplit(".", 1)[-1].isdigit()
                      and 2 <= int(x.rsplit(".", 1)[-1]) <= 99]
            if vraies:
                r["inscrit_dans"].append({"ip": ip, "liste": liste, "codes": vraies})
                r["problemes"].append(f"{ip} est inscrit dans {liste} ({', '.join(vraies)})")
            elif any(x.startswith("127.255.") for x in reponses):
                if liste not in r["non_verifiables"]:
                    r["non_verifiables"].append(liste)
    if r["non_verifiables"]:
        r["problemes"].append(
            "consultation refusée par " + ", ".join(r["non_verifiables"])
            + " (résolveur public) — l'inscription en liste noire n'est pas vérifiée")
    return r


# ── 3. Le fond : est-on lu ? ──────────────────────────────────────────────────
def _q(sql: str, params=None) -> list[tuple]:
    import pool_pg
    return pool_pg._q(sql, params or {})


def taux(site: str, jours: int = FENETRE_JOURS, mailbox: str | None = None,
         jusqu_a_il_y_a: int = 0) -> dict:
    """Ouverture, clic, rebond et plainte sur la fenêtre, en PERSONNES distinctes.

    On compte des personnes et non des événements : un prospect qui ouvre douze fois ne
    prouve pas douze fois que le message est arrivé, et une liste de diffusion qui
    recharge les images ferait passer un envoi en échec pour un succès.

    Les rebonds et les plaintes sont rapportés au volume envoyé sur la MÊME fenêtre, ce
    qui est la définition des fournisseurs.
    """
    # La boîte ne filtre que les ENVOIS, jamais les réactions : seul l'événement « sent »
    # porte une boîte expéditrice — une ouverture ou un rebond n'en portent pas. Filtrer
    # toute la fenêtre sur `mailbox` donnait donc 0 % d'ouverture pour chaque boîte, ce
    # qu'un premier jet a affiché en toute confiance sur quatre boîtes en bonne santé.
    # On sélectionne donc les destinataires servis PAR cette boîte, puis on mesure ce
    # qu'ils ont fait, quelle qu'en soit la trace.
    cond_boite = " AND ev.mailbox = %(mb)s" if mailbox else ""
    # `jusqu_a_il_y_a` exclut les N derniers jours. Sert à la RÉFÉRENCE : mesurer une
    # chute contre une moyenne qui contient déjà la chute la dilue un peu plus chaque
    # jour, et l'alerte finit par s'éteindre alors que le problème dure.
    cond_fin = (" AND ev.occurred_at < now() - make_interval(days => %(f)s)"
                if jusqu_a_il_y_a else "")
    p = {"site": site, "j": int(jours), "mb": mailbox, "f": int(jusqu_a_il_y_a)}
    r = _q(f"""
        WITH envoyes AS (
            SELECT DISTINCT ev.email FROM email_events ev
            WHERE ev.site_code = %(site)s AND ev.event_type = 'sent'
              AND ev.occurred_at >= now() - make_interval(days => %(j)s){cond_boite}{cond_fin}),
        reactions AS (
            SELECT ev.email, ev.event_type FROM email_events ev
            JOIN envoyes e ON e.email = ev.email
            WHERE ev.site_code = %(site)s AND ev.event_type <> 'sent'
              AND ev.occurred_at >= now() - make_interval(days => %(j)s){cond_fin})
        SELECT (SELECT count(*) FROM envoyes),
               count(DISTINCT f.email) FILTER (WHERE f.event_type = 'open'),
               count(DISTINCT f.email) FILTER (WHERE f.event_type = 'click'),
               count(DISTINCT f.email) FILTER (WHERE f.event_type = 'bounce'),
               count(DISTINCT f.email) FILTER (WHERE f.event_type = 'complaint'),
               count(DISTINCT f.email) FILTER (WHERE f.event_type = 'unsub')
        FROM reactions f""", p)
    envoyes, ouv, clic, reb, plainte, desab = (r[0] if r else (0, 0, 0, 0, 0, 0))
    envoyes = int(envoyes or 0)

    def pc(n) -> float | None:
        return round(100.0 * int(n or 0) / envoyes, 1) if envoyes else None

    return {"site": site, "boite": mailbox, "jours": jours, "envoyes": envoyes,
            "ouvreurs": int(ouv or 0), "cliqueurs": int(clic or 0),
            "rebonds": int(reb or 0), "plaintes": int(plainte or 0),
            "desabonnements": int(desab or 0),
            "taux_ouverture": pc(ouv), "taux_clic": pc(clic),
            "taux_rebond": pc(reb), "taux_plainte": pc(plainte),
            "concluant": envoyes >= VOLUME_MINIMUM}


CACHE_DNS = BASE_DIR / "memory" / "sante_envoi_dns.json"
CACHE_HEURES = 12


def _dns_du_jour(domaines: list[str], hotes: list[str], forcer: bool = False) -> dict:
    """Le volet DNS, relu au plus deux fois par jour.

    Les alertes tournent toutes les heures ; refaire à chaque passage une quarantaine de
    requêtes DNS — dont trente vers des listes noires publiques — c'est se faire limiter
    par les serveurs qu'on interroge, et transformer la surveillance en source de faux
    négatifs. Un enregistrement DNS ne change pas dans l'heure ; douze heures suffisent.
    """
    from datetime import datetime, timezone
    if not forcer:
        try:
            cache = json.loads(CACHE_DNS.read_text())
            age = (datetime.now(timezone.utc)
                   - datetime.fromisoformat(cache["releve_a"])).total_seconds() / 3600
            if age < CACHE_HEURES and cache.get("domaines_demandes") == domaines:
                cache["age_heures"] = round(age, 1)
                return cache
        except Exception:  # noqa: BLE001 — pas de cache lisible = on relève
            pass
    releve = {"releve_a": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "domaines_demandes": domaines,
              "domaines": [controler_domaine(d) for d in domaines],
              "listes_noires": [controler_listes_noires(h) for h in hotes],
              "age_heures": 0.0}
    try:
        CACHE_DNS.parent.mkdir(parents=True, exist_ok=True)
        CACHE_DNS.write_text(json.dumps(releve, ensure_ascii=False, indent=1))
    except Exception as e:  # noqa: BLE001
        print(f"[sante_envoi] relevé DNS non mis en cache : {e}", flush=True)
    return releve


def bilan(site: str = "lcr", forcer_dns: bool = False) -> dict:
    """Le tableau complet : forme, réputation, fond — par domaine et par boîte."""
    import expediteur

    boites = expediteur.boites(site)
    domaines = sorted({b["domaine"] for b in boites if b["domaine"]})
    hotes = sorted({b["smtp_host"] for b in boites if b.get("smtp_host")})
    dns = _dns_du_jour(domaines, hotes, forcer=forcer_dns)

    return {
        "site": site,
        "dns_releve_a": dns["releve_a"], "dns_age_heures": dns.get("age_heures"),
        "domaines": dns["domaines"],
        "listes_noires": dns["listes_noires"],
        "global": taux(site),
        # La référence longue : c'est elle qui donne son sens au chiffre de la semaine.
        # La référence s'arrête où commence la mesure : les deux fenêtres ne se
        # recouvrent pas, sinon on compare un chiffre à lui-même.
        "reference": taux(site, jours=FENETRE_REFERENCE, jusqu_a_il_y_a=FENETRE_JOURS),
        "par_boite": [dict(taux(site, mailbox=b["email"]),
                           daily_cap=b["daily_cap"], statut=b["status"],
                           envoyes_aujourdhui=b["envoyes_aujourdhui"]) for b in boites],
        "repartition_affinite": expediteur.repartition(site),
    }


# ── Ce qui déclenche une alerte ───────────────────────────────────────────────
def problemes(site: str = "lcr") -> dict[str, str]:
    """Problèmes de délivrabilité, sous des clés stables — au format de `alertes.py`.

    Une clé par problème et par objet concerné : deux boîtes en souffrance donnent deux
    alertes, et une boîte qui se rétablit fait disparaître la sienne sans effacer l'autre.
    """
    out: dict[str, str] = {}
    try:
        b = bilan(site)
    except Exception as e:  # noqa: BLE001
        return {"sante_envoi": f"📉 La surveillance de délivrabilité est en panne : {e}"}

    for d in b["domaines"]:
        for pb in d["problemes"]:
            cle = f"dns:{d['domaine']}:{pb.split()[0].lower()}"
            out[cle] = (f"📮 *{d['domaine']} — configuration d'envoi* : {pb}.\n"
                        f"   Tant que ce n'est pas corrigé, les messages partent mais "
                        f"n'arrivent pas.")
    for n in b["listes_noires"]:
        for inscription in n["inscrit_dans"]:
            out[f"blacklist:{inscription['ip']}:{inscription['liste']}"] = (
                f"⛔ *Serveur d'envoi en liste noire* : {inscription['ip']} figure dans "
                f"{inscription['liste']}.\n"
                f"   Les envois vers une partie des fournisseurs sont refusés. "
                f"Demander le retrait avant de reprendre les campagnes.")

    g = b["global"]
    # La chute relative, d'abord : elle se déclenche bien avant le plancher.
    ref = b.get("reference") or {}
    if (g["concluant"] and ref.get("concluant")
            and (ref.get("taux_ouverture") or 0) > 0
            and (g["taux_ouverture"] or 0) > 0):
        perte = 1 - (g["taux_ouverture"] / ref["taux_ouverture"])
        if perte >= CHUTE_OUVERTURE:
            out["ouverture:chute"] = (
                f"📉 *L'ouverture chute* : {g['taux_ouverture']} % sur {g['jours']} jours, "
                f"contre {ref['taux_ouverture']} % sur les {FENETRE_REFERENCE} derniers "
                f"({round(perte * 100)} % de moins).\n"
                f"   Le niveau reste correct, c'est la PENTE qui alerte — attendre le "
                f"plancher de {SEUIL_OUVERTURE} % reviendrait à prévenir une fois le "
                f"domaine abîmé. À regarder : un changement d'objet, de message, ou de "
                f"cible récent.")

    if g["concluant"]:
        if (g["taux_ouverture"] or 0) < SEUIL_OUVERTURE:
            out["ouverture:site"] = (
                f"📉 *Taux d'ouverture à {g['taux_ouverture']} %* sur {g['jours']} jours "
                f"({g['ouvreurs']} lecteurs pour {g['envoyes']} envois).\n"
                f"   Sous {SEUIL_OUVERTURE} %, le message n'est plus lu : il est classé. "
                f"À regarder dans l'ordre — la configuration du domaine, puis l'objet, "
                f"puis le contenu.")
        if (g["taux_rebond"] or 0) > SEUIL_REBOND:
            out["rebond:site"] = (
                f"📮 *Taux de rebond à {g['taux_rebond']} %* sur {g['jours']} jours "
                f"({g['rebonds']} rebonds pour {g['envoyes']} envois).\n"
                f"   Au-delà de {SEUIL_REBOND} %, les fournisseurs commencent à filtrer "
                f"le domaine entier. Vérifier la vérification Mailnjoy avant l'envoi.")
        if (g["taux_plainte"] or 0) > SEUIL_PLAINTE:
            out["plainte:site"] = (
                f"🚨 *Taux de plainte à {g['taux_plainte']} %* sur {g['jours']} jours "
                f"({g['plaintes']} plaintes).\n"
                f"   Le seuil de blocage des fournisseurs est à 0,3 % et se franchit en "
                f"une journée. Suspendre les envois et revoir le ciblage.")

    for bx in b["par_boite"]:
        if bx["concluant"] and (bx["taux_ouverture"] or 0) < SEUIL_OUVERTURE:
            out[f"ouverture:{bx['boite']}"] = (
                f"📉 *{bx['boite']}* : {bx['taux_ouverture']} % d'ouverture sur "
                f"{bx['jours']} jours ({bx['envoyes']} envois).\n"
                f"   Une seule boîte en dessous, les autres au-dessus : c'est la boîte "
                f"qu'il faut mettre au repos, pas la campagne.")
    return out


if __name__ == "__main__":
    import sys
    b = bilan("lcr", forcer_dns="--dns" in sys.argv)
    if "--json" in sys.argv:
        print(json.dumps(b, indent=2, ensure_ascii=False, default=str))
    else:
        for d in b["domaines"]:
            print(f"\n■ {d['domaine']}")
            print(f"   MX     : {', '.join(d['mx']) or '—'}")
            print(f"   SPF    : {d['spf'] or '—'}")
            print(f"   DKIM   : {d['dkim'] or '—'}")
            print(f"   DMARC  : {d['dmarc'] or '—'}")
            for x in d["problemes"]:
                print(f"   ✗ {x}")
            for x in d["avertissements"]:
                print(f"   ! {x}")
        for n in b["listes_noires"]:
            etat = "; ".join(f"{i['ip']} dans {i['liste']}" for i in n["inscrit_dans"]) \
                or ("non vérifiable : " + ", ".join(n["non_verifiables"])
                    if n.get("non_verifiables") else "")
            print(f"\n■ {n['hote']} ({', '.join(n['ips']) or '—'}) : "
                  f"{etat or 'aucune liste noire'}")
        g = b["global"]
        print(f"\n■ Fenêtre {g['jours']} jours — {g['envoyes']} envois")
        print(f"   ouverture {g['taux_ouverture']} %  ·  clic {g['taux_clic']} %  ·  "
              f"rebond {g['taux_rebond']} %  ·  plainte {g['taux_plainte']} %")
        for bx in b["par_boite"]:
            print(f"   {bx['boite']:32s} {bx['envoyes_aujourdhui']:3d}/{bx['daily_cap']:3d} "
                  f"aujourd'hui · ouverture {bx['taux_ouverture']} % sur {bx['envoyes']} envois")
        pbs = problemes("lcr")
        print(f"\n■ Alertes : {len(pbs)}")
        for k, v in pbs.items():
            print(f"   [{k}] {v.splitlines()[0]}")
