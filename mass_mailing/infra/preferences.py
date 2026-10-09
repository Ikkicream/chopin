"""mass_mailing/infra/preferences.py — la page derrière « ✉ Email envoyé par la technologie Cheffer ».

Demande de Camille (27/09/2026) : remplacer le lien piège invisible (1 px) par un badge VISIBLE en
pied de mail, qui mène à une page neutre Cheffer avec un formulaire d'« opt-down » (gérer la
pression marketing, se désabonner), « avec une logique à perdre un bot qui cherche sa route ».

- GET  /api/public/mass-mailing/p?t=…  : note la visite (un scanner suit tous les liens), affiche la
  page. Aucun lien sortant (rien à suivre pour un robot), noindex/nofollow. Un GET ne change RIEN.
- POST /api/public/mass-mailing/p      : applique le choix SEULEMENT si les preuves humaines sont là :
    1. champ piège `site_web` vide (caché aux humains, rempli par les robots qui remplissent tout) ;
    2. `geste` = preuve posée par le navigateur au premier vrai geste (souris, clavier, toucher) ;
    3. au moins DELAI_MIN_S secondes entre l'affichage et l'envoi (et au plus 2 h) ;
    4. jeton destinataire signé valide.
  Sinon : « C'est enregistré » quand même (le robot ne sait pas qu'il est repéré), rien n'est fait,
  l'essai est journalisé `robot_perdu` avec son motif.
- Pression marketing : `mensuel` (1 email Mass Email par 30 jours au plus) ou `pause` (90 jours).
  Respectée à l'envoi par `filtre_envoi()` (jobs/envoi.envoyer_lot).
"""
from __future__ import annotations

import hashlib
import hmac
import html as _h
import json
import time

from infra import desinscription, pg

DELAI_MIN_S = 3
DUREE_MAX_S = 7200
PAUSE_JOURS = 90
FENETRE_MENSUELLE_JOURS = 30

CHOIX = {
    "mensuel": "Recevoir au maximum 1 email par mois",
    "pause": "Faire une pause de 3 mois",
    "desinscription": "Ne plus rien recevoir (désabonnement)",
}


def _signe(t: str, emis: int) -> str:
    return hmac.new(desinscription._secret(), f"prefs|{t}|{emis}".encode(), hashlib.sha256).hexdigest()[:32]


def contexte(t: str) -> dict | None:
    rid = desinscription.lire_jeton(t)
    if rid is None:
        return None
    if rid == 0:
        # Lien d'un BAT (destinataire 0) : la page s'affiche en aperçu, rien n'est enregistré.
        return {"id": None, "campaign_id": None, "email_hash": None, "email_normalized": None,
                "from_name": None, "test": True}
    return pg.ligne("""SELECT r.id, r.campaign_id, r.email_hash, r.email_normalized, c.from_name
                         FROM recipients r JOIN campaigns c ON c.id = r.campaign_id WHERE r.id = %(i)s""", {"i": rid})


def journaliser(ctx: dict | None, action: str, ip: str, ua: str, motif: str | None = None) -> None:
    pg.ecrire("""INSERT INTO preferences_evenements (campaign_id, recipient_id, action, motif, ip, user_agent)
                 VALUES (%(c)s, %(r)s, %(a)s, %(m)s, %(ip)s, %(ua)s)""",
              {"c": ctx and ctx["campaign_id"], "r": ctx and ctx["id"], "a": action, "m": motif,
               "ip": (ip or "")[:64], "ua": (ua or "")[:500]})


_STYLE = """*{box-sizing:border-box}body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
background:#f6f6f7;color:#1f1f23;display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0;padding:16px}
main{background:#fff;border:1px solid #e7e7ea;border-radius:16px;padding:32px;max-width:460px;width:100%}
.marque{display:flex;align-items:center;gap:8px;font-weight:600;font-size:15px;color:#6d28d9;margin-bottom:18px}
h1{font-size:20px;margin:0 0 8px}p{color:#5f5f6b;line-height:1.5;margin:0 0 18px;font-size:14px}
label.choix{display:flex;gap:10px;align-items:flex-start;border:1px solid #e7e7ea;border-radius:12px;padding:12px 14px;margin-bottom:10px;cursor:pointer;font-size:14px}
label.choix:has(input:checked){border-color:#7c3aed;background:#f5f3ff}
button{width:100%;margin-top:8px;background:#111;color:#fff;border:0;border-radius:10px;padding:12px;font-size:15px;cursor:pointer}
button:disabled{opacity:.5;cursor:default}.ps{font-size:12px;color:#8a8a95;margin-top:16px;margin-bottom:0}
.hp{position:absolute;left:-10000px;top:auto;width:1px;height:1px;overflow:hidden}"""


def page(t: str, emetteur: str | None) -> str:
    emis = int(time.time())
    sig = _signe(t, emis)
    options = "".join(
        f'<label class="choix"><input type="radio" name="choix" value="{k}" required> <span>{_h.escape(v)}</span></label>'
        for k, v in CHOIX.items())
    qui = f" de la part de <b>{_h.escape(emetteur)}</b>" if emetteur else ""
    # Aucun <a href> : un robot qui « cherche sa route » ne trouve rien à suivre.
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow,noarchive">
<title>Cheffer · vos préférences email</title><style>{_STYLE}</style></head><body><main>
<div class="marque">✉ Cheffer</div>
<h1>Vos préférences email</h1>
<p>Cet email vous a été envoyé{qui} grâce à Cheffer, une technologie d’emailing. Vous pouvez choisir d’en recevoir moins, de faire une pause ou de ne plus rien recevoir.</p>
<form method="post" action="?t={_h.escape(t)}" autocomplete="off">
<input type="hidden" name="t" value="{_h.escape(t)}"><input type="hidden" name="emis" value="{emis}">
<input type="hidden" name="sig" value="{sig}"><input type="hidden" name="geste" id="geste" value="">
<div class="hp" aria-hidden="true"><label>Site web <input type="text" name="site_web" tabindex="-1" autocomplete="off"></label></div>
{options}
<button type="submit" id="ok" disabled>Enregistrer mes préférences</button>
</form>
<p class="ps">Aucun compte à créer. Votre choix s’applique à cette adresse email.</p>
</main><script>
(function(){{var fait=false;function preuve(){{if(fait)return;fait=true;
document.getElementById('geste').value='{sig}'.split('').reverse().join('');
document.getElementById('ok').disabled=false;}}
['pointerdown','keydown','touchstart'].forEach(function(e){{document.addEventListener(e,preuve,{{once:true,passive:true}})}});}})();
</script></body></html>"""


def merci(texte: str = "Vos préférences sont enregistrées. Merci !") -> str:
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow">
<title>Cheffer · c’est enregistré</title><style>{_STYLE}</style></head><body><main>
<div class="marque">✉ Cheffer</div><h1>C’est enregistré</h1><p>{_h.escape(texte)}</p></main></body></html>"""


def verifier_humain(form: dict, t: str, maintenant: float | None = None) -> str | None:
    """None si l'envoi porte les preuves d'un humain, sinon le motif (fonction pure, testée)."""
    maintenant = maintenant if maintenant is not None else time.time()
    if (form.get("site_web") or "").strip():
        return "champ piège rempli"
    try:
        emis = int(form.get("emis") or 0)
    except ValueError:
        return "horodatage illisible"
    sig = form.get("sig") or ""
    if not hmac.compare_digest(sig, _signe(t, emis)):
        return "signature invalide"
    if (form.get("geste") or "") != sig[::-1]:
        return "aucun geste humain (pas de souris, clavier ni toucher)"
    ecart = maintenant - emis
    if ecart < DELAI_MIN_S:
        return f"envoyé {ecart:.1f} s après l'affichage (trop rapide)"
    if ecart > DUREE_MAX_S:
        return "formulaire trop ancien"
    if form.get("choix") not in CHOIX:
        return "choix inconnu"
    return None


def appliquer(ctx: dict, choix: str) -> None:
    if choix == "desinscription":
        pg.ecrire("""INSERT INTO suppressions (email_hash, email_normalized, reason, source, scope, metadata)
                     VALUES (%(h)s, %(e)s, 'unsubscribe', 'page_preferences', 'global', %(m)s::jsonb)
                     """ + pg.SUPPRESSION_SUR_CONFLIT,
                  {"h": ctx["email_hash"], "e": ctx["email_normalized"],
                   "m": json.dumps({"campaign_id": str(ctx["campaign_id"]), "recipient_id": ctx["id"]})})
        pg.ecrire("UPDATE recipients SET unsubscribed_at = COALESCE(unsubscribed_at, now()), updated_at = now() WHERE id = %(i)s",
                  {"i": ctx["id"]})
        return
    pg.ecrire("""INSERT INTO preferences (email_hash, mode, jusqu_a, updated_at)
                 VALUES (%(h)s, %(m)s, CASE WHEN %(m)s = 'pause' THEN now() + make_interval(days => %(j)s) END, now())
                 ON CONFLICT (email_hash) DO UPDATE SET mode = EXCLUDED.mode, jusqu_a = EXCLUDED.jusqu_a, updated_at = now()""",
              {"h": ctx["email_hash"], "m": choix, "j": PAUSE_JOURS})


def filtre_envoi(sending_batch_id: str) -> int:
    """Juste avant un lot : écarte les destinataires en pause, ou limités à 1 email par mois et
    déjà servis par une autre campagne Mass Email dans les 30 derniers jours."""
    n = pg.ecrire("""
        UPDATE recipients r SET send_status = 'skipped', eligibility_status = 'excluded',
               eligibility_reason = CASE WHEN p.mode = 'pause' THEN 'preference_pause' ELSE 'preference_mensuel' END,
               updated_at = now()
          FROM preferences p
         WHERE r.sending_batch_id = %(s)s AND r.send_status = 'queued' AND p.email_hash = r.email_hash
           AND ((p.mode = 'pause' AND p.jusqu_a > now())
                OR (p.mode = 'mensuel' AND EXISTS (
                        SELECT 1 FROM recipients x WHERE x.email_hash = r.email_hash AND x.id <> r.id
                           AND x.submitted_at > now() - make_interval(days => %(f)s))))""",
              {"s": sending_batch_id, "f": FENETRE_MENSUELLE_JOURS})
    return n or 0
