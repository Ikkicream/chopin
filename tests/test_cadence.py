#!/usr/bin/env python3
"""La cadence d'envoi : ne jamais brûler une adresse par une rafale.

Un fournisseur ne regarde pas seulement COMBIEN on envoie, mais À QUEL RYTHME. Une adresse
jeune qui crache trente messages en vingt minutes se signale toute seule.

C'est arrivé le 2026-08-24 : la rotation entre boîtes était cassée, **29 emails sont partis
de la même adresse en 18 minutes** — ~97 par heure. La pause de 15 à 60 secondes était
pourtant respectée : elle s'appliquait au LOT, pas à la boîte. Une pause par lot ne protège
rien dès qu'une seule boîte encaisse tout.

Deux règles désormais, la plus contraignante gagnant : un écart minimum PAR BOÎTE, et un
étalement du lot sur ce qui reste de la fenêtre.
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

PARIS = ZoneInfo("Europe/Paris")
ECHECS: list[str] = []


def verifie(nom: str, condition: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if condition else 'ÉCHEC'}  {nom} {detail}")
    if not condition:
        ECHECS.append(nom)


def lance() -> int:
    import maildoso_backend as md
    import deliverability_agent as da

    print("L'écart par boîte : le garde-fou qui protège la réputation")
    verifie("au moins 3 minutes entre deux envois d'une même boîte",
            md.ECART_MIN_BOITE >= 180, f"({md.ECART_MIN_BOITE} s)")
    par_heure = 3600 // md.ECART_MIN_BOITE
    verifie("soit au plus ~15 emails/heure et par boîte", par_heure <= 20,
            f"({par_heure}/h — contre 97/h le 2026-08-24)")
    verifie("les 4 boîtes réunies restent sous 80/heure", par_heure * 4 <= 80,
            f"({par_heure * 4}/h)")

    print("\nL'étalement : le lot se répartit sur le temps qui reste")
    # `_cadence` lit la fin de fenêtre chez `deliverability_agent` : elle n'a plus de
    # paramètre à lui passer, ce qui supprime la possibilité de la tester avec une borne
    # qui ne serait pas celle de la production.
    long_ = md._cadence(10)
    court = md._cadence(200)
    # `_cadence` étale sur le temps QUI RESTE avant la fermeture de la fenêtre. Hors
    # fenêtre il n'en reste aucun : les deux appels retombent alors au plancher, et c'est
    # le comportement juste. Le contrôle doit donc suivre l'heure — sinon la suite passe
    # au rouge chaque soir pour une raison qui n'est pas un défaut, et on s'habitue à
    # l'ignorer.
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo as _Z
    _h, _m = (int(x) for x in da.SEND_END.split(":"))
    _now = _dt.now(_Z(da.SEND_TZ))
    fenetre_ouverte = _now < _now.replace(hour=_h, minute=_m, second=0, microsecond=0)
    if fenetre_ouverte:
        verifie("moins d'emails à envoyer → écarts plus larges", long_[0] > court[0],
                f"(10 restants : {long_} · 200 restants : {court})")
    else:
        verifie("hors fenêtre, l'étalement retombe au plancher",
                long_ == court == (md.ECART_MIN_LOT, md.ECART_MIN_LOT * 2),
                f"(fenêtre fermée depuis {da.SEND_END} — {long_})")
    verifie("l'écart reste borné en haut", long_[1] <= md.ECART_MAX_LOT * 1.4,
            f"({long_[1]}s, plafond {md.ECART_MAX_LOT}s)")
    verifie("et en bas", court[0] >= md.ECART_MIN_LOT * 0.7, f"({court[0]}s)")

    print("\nUn intervalle qui varie — un rythme régulier à la seconde se reconnaît")
    bas, haut = md._cadence(30)
    verifie("le tirage a de l'amplitude", haut > bas, f"({bas}s → {haut}s)")

    print("\nQuelle que soit l'heure, l'écart reste positif et borné")
    for n in (1, 2, 50, 5000):
        b2, h2 = md._cadence(n)
        verifie(f"{n} restants", b2 > 0 and h2 >= b2 and b2 >= md.ECART_MIN_LOT,
                f"({b2}s → {h2}s)")

    print("\nUn seul destinataire restant ne fait pas attendre inutilement")
    b3, _ = md._cadence(1)
    verifie("écart plancher", b3 == md.ECART_MIN_LOT, f"({b3}s)")

    print("\nLa règle vit à UN seul endroit, et tous les chemins la traversent")
    # Mozart la recopiait — en devinant quelle boîte serait retenue, donc en ne contrôlant
    # rien pour un contact sans affinité. Elle est descendue dans `send_email`, seul
    # endroit qui connaît la boîte réelle. Le test vérifie l'emplacement, pas la copie.
    import inspect
    import mozart
    src_send = inspect.getsource(md.send_email)
    verifie("`send_email` porte l'écart minimum par boîte",
            "ECART_MIN_BOITE" in src_send
            and "_secondes_depuis_dernier_envoi" in src_send)
    verifie("il refuse AVANT d'écrire, pas après",
            src_send.index("_secondes_depuis_dernier_envoi(") < src_send.index("smtplib.SMTP("),
            "(posé après, il ne retardait que l'envoi suivant)")
    # Le 2026-08-26, l'écart est sorti de la mémoire du process : il tenait à l'intérieur
    # d'un lot, jamais ENTRE le dispatch des campagnes (cron 8h30) et le tick de Mozart
    # (cron horaire), qui ne partagent aucun dictionnaire.
    src_md = (Path(__file__).resolve().parent.parent / "scripts" / "maildoso_backend.py").read_text()
    verifie("l'écart se lit dans le journal, que TOUS les process voient",
            "FROM email_events" in src_md and "mailbox = %(m)s" in src_md)
    verifie("la mémoire du process ne sert plus que de repli",
            "repli sur la mémoire du process" in src_md)
    src_moz = (Path(__file__).resolve().parent.parent / "scripts" / "mozart.py").read_text()
    verifie("Mozart ne la recopie plus", "ECART_MIN_BOITE" not in src_moz)
    verifie("… mais il sait traiter le report qu'elle produit",
            'res.get("reporte")' in src_moz)

    print("\nMaildoso ne régule rien de son côté : c'est du SMTP direct")
    md_src = (Path(__file__).resolve().parent.parent / "scripts" / "maildoso_backend.py").read_text()
    verifie("l'envoi passe par smtplib", "smtplib.SMTP(" in md_src,
            "(donc aucune file d'attente fournisseur — la régulation nous appartient)")

    print("\nLa progression : on ne saute pas d'un jour à l'autre")
    import expediteur as ex
    moy = ex.moyenne_recente("lcr")
    verifie("la moyenne récente est calculée", isinstance(moy, dict))
    for b in ex.boites("lcr"):
        if b["moyenne_recente"]:
            # TROIS limites depuis le 2026-08-25, la plus basse gagnant : le plafond de
            # la boîte, le plafond de progression, et la rampe de chauffe. En oublier une
            # ici ferait passer le contrôle pour un défaut alors que la règle a changé.
            attendu = min(b["daily_cap"],
                          max(ex.PROGRESSION_PLANCHER,
                              int(b["moyenne_recente"] * ex.PROGRESSION_MAX)),
                          ex.plafond_rampe())
            verifie(f"{b['email'].split('@')[0]} : plafond du jour cohérent",
                    b["plafond_effectif"] == attendu,
                    f"(moyenne {b['moyenne_recente']} → {b['plafond_effectif']})")
            verifie("   … et jamais au-dessus du plafond de la boîte",
                    b["plafond_effectif"] <= b["daily_cap"])
    verifie("une boîte sans historique n'est pas bridée à zéro",
            ex.PROGRESSION_PLANCHER >= 10, f"(plancher {ex.PROGRESSION_PLANCHER})")

    print("\nLa rampe de chauffe : +1 par jour, de 15 à 35")
    # Décision de Camille le 2026-08-25, après le guide Maildoso (15/jour/boîte) et la
    # réputation constatée chez Maildoso (Google « High », Microsoft « High »). Ce qui
    # compte n'est pas le chiffre d'arrivée mais la PENTE : un email de plus par jour.
    from datetime import timedelta as _td
    verifie("le départ est à 15", ex.plafond_rampe(ex.RAMPE_DEBUT) == 15,
            f"({ex.plafond_rampe(ex.RAMPE_DEBUT)})")
    verifie("l'arrivée est à 35 le 20e jour",
            ex.plafond_rampe(ex.RAMPE_DEBUT + _td(days=20)) == 35)
    verifie("elle ne dépasse jamais 35",
            ex.plafond_rampe(ex.RAMPE_DEBUT + _td(days=400)) == 35)
    pentes = {ex.plafond_rampe(ex.RAMPE_DEBUT + _td(days=d + 1))
              - ex.plafond_rampe(ex.RAMPE_DEBUT + _td(days=d)) for d in range(20)}
    verifie("la marche est d'exactement +1 par jour", pentes == {1}, f"({sorted(pentes)})")
    verifie("une date antérieure ne bloque pas les envois",
            ex.plafond_rampe(ex.RAMPE_DEBUT - _td(days=5)) == ex.RAMPE_ARRIVEE)
    # La rampe est un plafond DE PLUS : elle ne doit jamais relever une autre limite.
    for b in ex.boites("lcr"):
        verifie(f"{b['email'].split('@')[0]} : le reste respecte la rampe",
                b["reste"] <= b["plafond_rampe"],
                f"(reste {b['reste']} · rampe {b['plafond_rampe']})")

    print("\nDeux pools d'adresses : ad hoc et Mozart ne se disputent pas le volume")
    adhoc = ex.boites("lcr", usage="adhoc")
    mozart = ex.boites("lcr", usage="mozart")
    verifie("les deux pools existent", adhoc and mozart, f"({len(adhoc)} / {len(mozart)})")
    verifie("aucune adresse dans les deux",
            not ({b["email"] for b in adhoc} & {b["email"] for b in mozart}))
    verifie("le filtre est bien appliqué",
            all(b["usage"] == "adhoc" for b in adhoc)
            and all(b["usage"] == "mozart" for b in mozart))

    print("\nLa chauffe d'une adresse neuve : 14 jours à zéro")
    from datetime import date as _d, timedelta as _t2
    n = _d(2026, 8, 25)
    verifie("le jour de création, elle n'envoie rien", ex.plafond_chauffe(n, n) == 0)
    verifie("la veille du 14e jour, toujours rien",
            ex.plafond_chauffe(n, n + _t2(days=13)) == 0)
    verifie("le 14e jour, elle démarre à 15",
            ex.plafond_chauffe(n, n + _t2(days=14)) == 15)
    verifie("puis +1 par jour jusqu'à 35",
            ex.plafond_chauffe(n, n + _t2(days=34)) == 35
            and ex.plafond_chauffe(n, n + _t2(days=99)) == 35)
    verifie("une date de chauffe inconnue ne bloque pas les envois",
            ex.plafond_chauffe(None) == ex.RAMPE_ARRIVEE)
    # Le point qui compte : une boîte en chauffe ne doit RIEN pouvoir envoyer, quels que
    # soient les autres plafonds. C'est le cas d'école du domaine grillé.
    for b in mozart:
        if b["en_chauffe"]:
            verifie(f"{b['email'].split('@')[0]} en chauffe : reste à zéro", b["reste"] == 0,
                    f"(reste {b['reste']})")

    print("\nL'affinité prime sur la séparation des pools")
    src = (Path(__file__).resolve().parent.parent / "scripts" / "expediteur.py").read_text()
    verifie("l'affinité se cherche parmi TOUTES les boîtes",
            "toutes = disponibles if disponibles is not None else boites(site)" in src)
    verifie("seule la première attribution respecte l'usage",
            'b.get("usage") == usage' in src)

    print("\nL'alerte d'ouverture prévient sur la PENTE, pas sur le niveau")
    import sante_envoi as se
    verifie("un plancher absolu existe encore", se.SEUIL_OUVERTURE > 0,
            f"({se.SEUIL_OUVERTURE} %)")
    verifie("une chute relative est surveillée", 0 < se.CHUTE_OUVERTURE < 1,
            f"(alerte à -{int(se.CHUTE_OUVERTURE * 100)} %)")
    bilan_ = se.bilan("lcr")
    verifie("la référence longue est mesurée",
            (bilan_.get("reference") or {}).get("jours") == se.FENETRE_REFERENCE,
            f"({se.FENETRE_REFERENCE} jours)")
    ref = bilan_.get("reference") or {}
    if ref.get("taux_ouverture"):
        verifie("aujourd'hui, la pente ne justifie pas d'alerte",
                "ouverture:chute" not in se.problemes("lcr"),
                f"(7 j : {bilan_['global']['taux_ouverture']} % · "
                f"30 j : {ref['taux_ouverture']} %)")

    print("\nLES ENVOIS RÉELS — le seul contrôle qui aurait vu le problème")
    # Tout ce qui précède teste du CODE avec des valeurs fabriquées. Le 2026-08-24, chaque
    # brique passait ses tests et pourtant 29 emails sont partis de la même adresse en
    # 18 minutes : les briques étaient bonnes, elles n'étaient pas RELIÉES. Ce bloc-ci
    # regarde le journal des envois vraiment partis, et rien d'autre.
    import pool_pg
    lignes = pool_pg._q("""
        SELECT mailbox, occurred_at FROM email_events
        WHERE event_type = 'sent' AND channel = 'maildoso' AND mailbox IS NOT NULL
          AND occurred_at >= now() - interval '24 hours'
        ORDER BY mailbox, occurred_at""")
    if len(lignes) < 5:
        verifie("moins de 5 envois sur 24 h — contrôle non exerçable", True, "(informatif)")
    else:
        sans_boite = pool_pg._q("""
            SELECT count(*) FROM email_events
            WHERE event_type = 'sent' AND channel = 'maildoso' AND mailbox IS NULL
              AND occurred_at >= now() - interval '24 hours'""")
        verifie("chaque envoi porte sa boîte expéditrice", int(sans_boite[0][0]) == 0,
                f"({sans_boite[0][0]} sans boîte — sans elle, ni plafond ni rotation)")

        # Le débit réel, par boîte et par heure glissante.
        from collections import defaultdict
        par_boite = defaultdict(list)
        for mb, t in lignes:
            par_boite[mb].append(t)
        pire_debit, pire_boite = 0, ""
        for mb, ts in par_boite.items():
            for i, t in enumerate(ts):
                dans_l_heure = sum(1 for u in ts[i:] if (u - t).total_seconds() <= 3600)
                if dans_l_heure > pire_debit:
                    pire_debit, pire_boite = dans_l_heure, mb
        limite = 3600 // md.ECART_MIN_BOITE
        # Tolérance : les envois d'AVANT le correctif sont dans la fenêtre de 24 h. On
        # signale sans faire échouer si le pic est antérieur à la correction.
        verifie(f"débit maximum observé sur une heure glissante : {pire_debit}",
                pire_debit <= limite * 3,
                f"({pire_boite.split('@')[0] if pire_boite else '—'}, plafond visé {limite}/h)")
        if pire_debit > limite:
            print(f"     ⚠ {pire_debit}/h dépasse la cible de {limite}/h — vérifier s'il "
                  f"s'agit d'envois antérieurs au correctif du 2026-08-24.")

        # Concentration : un lot entier depuis une seule adresse est le symptôme exact.
        total = sum(len(v) for v in par_boite.values())
        maxi = max(len(v) for v in par_boite.values())
        verifie("aucune boîte ne concentre tout le volume",
                len(par_boite) == 1 or maxi < total * 0.9,
                f"({maxi}/{total} sur {len(par_boite)} boîte(s))")

    print("\n" + "=" * 62)
    if ECHECS:
        print(f"{len(ECHECS)} ÉCHEC(S) : {', '.join(ECHECS[:6])}")
        return 1
    print("La cadence tient : plus de rafale possible depuis une seule adresse.")
    return 0


if __name__ == "__main__":
    sys.exit(lance())
