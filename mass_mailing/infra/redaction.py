#!/usr/bin/env python3
"""mass_mailing/infra/redaction.py — l'objet, le pré-en-tête et la version texte, proposés
à partir du HTML (Camille, 2026-09-25 : « je n'ai pas envie de chercher l'objet »).

Rend : un objet recommandé + 2 variantes, un pré-en-tête, et une version texte simple
mais efficace, injectée dans Sweego (`message-txt`). Tout reste modifiable à l'écran.

⚠️ Pas d'API Anthropic ici : Genesis l'a retirée volontairement (« la clé Anthropic
facturait par token et a coûté ~2000 $ », scripts/llm_call.py) et route tout vers
DeepSeek. Ce module fait de même, en COPIE AUTONOME (rien importé de scripts/) :
API compatible OpenAI, mode JSON. Les jetons consommés sont renvoyés pour être tracés.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import requests

MODELE = "deepseek-chat"
URL = "https://api.deepseek.com/chat/completions"
BASE_DIR = Path(__file__).resolve().parent.parent.parent

CONSIGNES = """Tu es un spécialiste de l'emailing B2B en français. On te donne le HTML d'un email
marketing envoyé à des professionnels. Rédige :

1. `objet` : l'objet le plus susceptible d'être ouvert, fidèle au contenu. 30 à 55 caractères
   idéalement, clair et concret, sans majuscules abusives, sans « RE: » ni « TR: », sans point
   d'exclamation multiple, sans mots qui déclenchent les filtres anti-spam (gratuit, urgent,
   offre exclusive, cliquez ici, 100 %…). Pas de promesse que le message ne tient pas.
2. `objets_alternatifs` : exactement 2 autres objets d'angle différent (bénéfice, question, chiffre).
3. `preheader` : 40 à 100 caractères qui complètent l'objet sans le répéter.
4. `texte` : la version texte brut du message, pour les messageries qui n'affichent pas le HTML.
   Fidèle au contenu, mais simple et efficace : paragraphes courts, une ligne vide entre eux,
   les listes en « - », chaque lien écrit « libellé : https://… » sur sa ligne (garde les URL
   exactes du HTML), aucun HTML ni Markdown. N'ajoute PAS de mention de désinscription ni de
   « voir la version en ligne » : ils sont ajoutés automatiquement.
5. `justification` : une phrase sur le choix de l'objet.

Réponds en français, UNIQUEMENT par un objet JSON de cette forme exacte :
{"objet": "...", "objets_alternatifs": ["...", "..."], "preheader": "...", "texte": "...", "justification": "..."}"""


def _cle() -> str:
    cle = os.environ.get("DEEPSEEK_API_KEY", "")
    env = BASE_DIR / ".env"
    if not cle and env.exists():
        for ligne in env.read_text().splitlines():
            ligne = ligne.strip()
            if ligne.startswith("DEEPSEEK_API_KEY="):
                cle = ligne.split("=", 1)[1].strip().strip("'\"")
                break
    if not cle:
        raise RuntimeError("DEEPSEEK_API_KEY introuvable (environnement ou .env)")
    return cle


def _alleger(html: str) -> str:
    """Retire ce qui n'est pas du contenu (styles, scripts, commentaires, blocs techniques
    ajoutés par Cheffer). Le texte et les liens restent intacts."""
    h = re.sub(r"(?is)<(style|script|head)\b.*?</\1\s*>", " ", html or "")
    h = re.sub(r"(?s)<!--.*?-->", " ", h)
    h = re.sub(r'(?is)<div class="mm-(preheader|miroir)".*?</div>', " ", h)
    return re.sub(r"\s{2,}", " ", h).strip()


def proposer(html: str, *, expediteur: str = "", objet_actuel: str = "") -> dict:
    contenu = _alleger(html)
    if not contenu:
        raise ValueError("message vide")
    contexte = f"Expéditeur : {expediteur or 'non précisé'}."
    if objet_actuel:
        contexte += f" Objet actuel (à améliorer si possible) : « {objet_actuel} »."
    r = requests.post(URL, timeout=120, headers={"Authorization": f"Bearer {_cle()}"}, json={
        "model": MODELE,
        "max_tokens": 4000,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": CONSIGNES},
                     {"role": "user", "content": f"{contexte}\n\nHTML de l'email :\n{contenu}"}],
    })
    if r.status_code != 200:
        raise RuntimeError(f"DeepSeek {r.status_code} : {r.text[:200]}")
    d = r.json()
    choix = d["choices"][0]
    if choix.get("finish_reason") == "length":
        raise RuntimeError("réponse tronquée (message trop long)")
    data = json.loads(choix["message"]["content"])
    manquants = [k for k in ("objet", "preheader", "texte") if not str(data.get(k) or "").strip()]
    if manquants:
        raise RuntimeError(f"réponse incomplète : {', '.join(manquants)}")
    data["objets_alternatifs"] = [o for o in (data.get("objets_alternatifs") or []) if o][:2]
    data["modele"] = MODELE
    u = d.get("usage") or {}
    data["usage"] = {"entree": u.get("prompt_tokens"), "sortie": u.get("completion_tokens")}
    return data
