#!/usr/bin/env python3
"""booking_page.py — Page publique de prise de RDV (HTML autonome, servie par FastAPI).

Rendu serveur minimal + JS vanilla qui consomme les endpoints publics :
  GET  /api/book/{site}/config         → motifs + jours réservables + meta
  GET  /api/book/{site}/slots?date=…   → créneaux libres d'un jour
  POST /api/book/{site}/submit         → crée le RDV + envoie email/SMS
"""
from __future__ import annotations

import html as _html
import json
import re as _re


def _domain(url: str) -> str:
    s = (url or "").replace("https://", "").replace("http://", "").strip("/")
    return s.split("/")[0]


def _safe_color(c: str) -> str:
    """N'autorise qu'une couleur hex — sinon fallback (anti-injection CSS via --brand)."""
    c = (c or "").strip()
    return c if _re.match(r"^#[0-9A-Fa-f]{3,8}$", c) else "#4f46e5"


def render_page(site: str, cfg: dict) -> str:
    label = _html.escape(cfg.get("from_name") or site.upper())
    color = _safe_color(cfg.get("brand_color"))
    logo = _html.escape(cfg.get("logo_url") or "")
    hero = _html.escape(cfg.get("hero_image_url") or "")
    website = _html.escape(cfg.get("website_url") or "")
    description = _html.escape(cfg.get("description") or "Choisissez un motif, un créneau, et c'est réglé.")
    domain = _domain(cfg.get("website_url") or "")
    favicon = (f"https://www.google.com/s2/favicons?domain={domain}&sz=64") if domain else ""
    # En-tête : logo image si fourni, sinon le nom du site en gros.
    header_brand = (f'<img src="{logo}" alt="{label}" style="max-height:48px;max-width:200px;margin-bottom:10px;display:block;">'
                    if logo else f'<div class="eyebrow">{label}</div>')
    # Lien « icône du site web » cliquable (favicon + nom de domaine).
    website_link = (f'<a href="{website}" target="_blank" rel="noopener" class="site-link">'
                    + (f'<img src="{favicon}" alt="" width="16" height="16">' if favicon else "")
                    + f'<span>{domain}</span></a>') if website else ""
    # En-tête en 2 colonnes : texte à gauche, image ENTIÈRE à droite (pas de recadrage).
    hero_img = f'<div class="head-img"><img src="{hero}" alt=""></div>' if hero else ""
    head_class = " has-hero" if hero else ""
    site_js = json.dumps(site)
    return r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Prendre rendez-vous — __LABEL__</title>
__FAVICON_LINK__
<style>
  :root { --brand: __COLOR__; }
  * { box-sizing: border-box; }
  body { margin:0; font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
         background:linear-gradient(135deg,#f8fafc,#eef2ff); color:#0f172a; min-height:100vh; }
  .wrap { max-width:680px; margin:0 auto; padding:32px 20px 60px; }
  .card { background:#fff; border-radius:20px; box-shadow:0 10px 40px rgba(15,23,42,.08); overflow:hidden; }
  .head { background:var(--brand); color:#fff; padding:0;
          display:flex; align-items:stretch; gap:0; }
  .head-text { flex:1; min-width:0; padding:32px 36px; }
  .head-img { flex:0 0 40%; max-width:40%; }
  .head-img img { display:block; width:100%; height:100%; object-fit:cover; object-position:center; }
  .head .eyebrow { font-size:12px; text-transform:uppercase; letter-spacing:1px; opacity:.85; }
  .head h1 { margin:8px 0 0; font-size:26px; font-weight:800; }
  .head p { margin:8px 0 0; font-size:14px; opacity:.9; line-height:1.45; }
  @media (max-width:560px) {
    .head { flex-direction:column; align-items:stretch; }
    .head-img { flex-basis:auto; max-width:100%; width:100%; order:-1; }
    .head-img img { height:160px; }
  }
  .site-link { display:inline-flex; align-items:center; gap:6px; margin-top:14px; padding:6px 12px;
               background:rgba(255,255,255,.18); border-radius:999px; color:#fff; text-decoration:none;
               font-size:13px; font-weight:600; }
  .site-link img { border-radius:3px; display:block; }
  .body { padding:28px 36px 36px; }
  .step-title { font-size:13px; font-weight:700; text-transform:uppercase; letter-spacing:.5px;
                color:#64748b; margin:26px 0 12px; }
  .reasons, .days, .slots { display:grid; gap:10px; }
  .reasons { grid-template-columns:1fr; }
  .days { grid-template-columns:repeat(auto-fill,minmax(110px,1fr)); }
  .slots { grid-template-columns:repeat(auto-fill,minmax(86px,1fr)); }
  .opt { border:1.5px solid #e2e8f0; border-radius:12px; padding:14px 16px; cursor:pointer;
         background:#fff; font-size:15px; transition:all .15s; text-align:left; }
  .opt:hover { border-color:var(--brand); }
  .opt.sel { border-color:var(--brand); background:color-mix(in srgb, var(--brand) 8%, #fff);
             box-shadow:0 0 0 3px color-mix(in srgb, var(--brand) 18%, transparent); }
  .opt .emoji { font-size:18px; margin-right:8px; }
  .day .dow { font-size:11px; text-transform:uppercase; color:#64748b; }
  .day .dnum { font-size:18px; font-weight:700; }
  .slot { text-align:center; padding:11px 8px; font-weight:600; }
  label.fld { display:block; margin:14px 0 6px; font-size:13px; font-weight:600; color:#334155; }
  input, textarea { width:100%; padding:12px 14px; border:1.5px solid #e2e8f0; border-radius:12px;
                    font-size:15px; font-family:inherit; }
  input:focus, textarea:focus { outline:none; border-color:var(--brand); }
  .btn { margin-top:22px; width:100%; background:var(--brand); color:#fff; border:none;
         border-radius:14px; padding:16px; font-size:16px; font-weight:700; cursor:pointer; }
  .btn:disabled { opacity:.5; cursor:not-allowed; }
  .hidden { display:none; }
  .muted { color:#94a3b8; font-size:14px; padding:10px 0; }
  .done { text-align:center; padding:30px 10px; }
  .done .check { width:64px;height:64px;border-radius:50%;background:#10b981;color:#fff;
                 font-size:34px;line-height:64px;margin:0 auto 16px; }
  .done h2 { margin:0 0 8px; font-size:22px; }
  .err { background:#fef2f2; color:#b91c1c; border:1px solid #fecaca; border-radius:12px;
         padding:12px 14px; margin-top:14px; font-size:14px; }
</style>
</head>
<body>
<div class="wrap">
  <div class="card">
    <div class="head__HEAD_CLASS__">
      <div class="head-text">
        __HEADER_BRAND__
        <h1>Prenons rendez-vous</h1>
        <p>__DESCRIPTION__</p>
        __WEBSITE_LINK__
      </div>
      __HERO_IMG__
    </div>
    <div class="body" id="form-view">
      <div class="step-title">1 · Motif du rendez-vous</div>
      <div class="reasons" id="reasons"></div>

      <div id="step-day" class="hidden">
        <div class="step-title">2 · Choisissez un jour</div>
        <div class="days" id="days"></div>
      </div>

      <div id="step-slot" class="hidden">
        <div class="step-title">3 · Choisissez un créneau</div>
        <div class="slots" id="slots"></div>
      </div>

      <div id="step-info" class="hidden">
        <div class="step-title">4 · Vos coordonnées</div>
        <label class="fld">Nom complet *</label>
        <input id="f-name" placeholder="Jean Dupont" autocomplete="name">
        <label class="fld">Email *</label>
        <input id="f-email" type="email" placeholder="jean@exemple.com" autocomplete="email">
        <label class="fld">Téléphone (pour le SMS de confirmation)</label>
        <input id="f-phone" type="tel" placeholder="06 12 34 56 78" autocomplete="tel">
        <label class="fld">Message (optionnel)</label>
        <textarea id="f-msg" rows="3" placeholder="Un contexte utile ?"></textarea>
        <div id="err" class="err hidden"></div>
        <button class="btn" id="submit-btn" disabled>Confirmer le rendez-vous</button>
      </div>
    </div>

    <div class="body hidden" id="done-view">
      <div class="done">
        <div class="check">✓</div>
        <h2>Rendez-vous confirmé !</h2>
        <p class="muted" id="done-msg"></p>
      </div>
    </div>
  </div>
</div>

<script>
const SITE = __SITE__;
const API = "/api/book/" + SITE;
const st = { reason:null, day:null, slot:null };

function fmtDay(iso){
  const d = new Date(iso + "T00:00:00");
  const dow = ["DIM","LUN","MAR","MER","JEU","VEN","SAM"][d.getDay()];
  return {dow, dnum: d.getDate(), mon: d.toLocaleDateString("fr-FR",{month:"short"})};
}
function show(id, on){ document.getElementById(id).classList.toggle("hidden", !on); }
function clearSel(container){ [...container.children].forEach(c=>c.classList.remove("sel")); }
const EMAIL_RE = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/;
function refreshSubmit(){
  const email = document.getElementById("f-email").value.trim();
  const emailOk = EMAIL_RE.test(email);
  const ok = st.reason && st.slot && document.getElementById("f-name").value.trim() && emailOk;
  document.getElementById("submit-btn").disabled = !ok;
  const err = document.getElementById("err");
  if (email && !emailOk) { err.textContent = "Adresse email invalide."; err.classList.remove("hidden"); }
  else if (!err.textContent.startsWith("Erreur")) { err.classList.add("hidden"); }
}

async function init(){
  const r = await fetch(API + "/config");
  const cfg = await r.json();
  const rc = document.getElementById("reasons");
  (cfg.reasons||[]).forEach(reason=>{
    const el = document.createElement("button");
    el.className = "opt";
    const em = document.createElement("span"); em.className = "emoji"; em.textContent = reason.emoji || "📌";
    el.appendChild(em);
    el.appendChild(document.createTextNode(reason.label || ""));
    el.onclick = ()=>{ clearSel(rc); el.classList.add("sel"); st.reason=reason.key;
                       loadDays(cfg.days||[]); show("step-day", true); refreshSubmit(); };
    rc.appendChild(el);
  });
}
function loadDays(days){
  const dc = document.getElementById("days"); dc.innerHTML="";
  if(!days.length){ dc.innerHTML='<div class="muted">Aucune disponibilité pour le moment.</div>'; return; }
  days.forEach(day=>{
    const f = fmtDay(day.date);
    const el = document.createElement("button");
    el.className = "opt day";
    el.innerHTML = '<div class="dow">'+f.dow+'</div><div class="dnum">'+f.dnum+'</div><div class="dow">'+f.mon+'</div>';
    el.onclick = ()=>{ clearSel(dc); el.classList.add("sel"); st.day=day.date; st.slot=null;
                       loadSlots(day.date); show("step-slot", true); show("step-info", false); refreshSubmit(); };
    dc.appendChild(el);
  });
}
async function loadSlots(date){
  const sc = document.getElementById("slots"); sc.innerHTML='<div class="muted">Chargement…</div>';
  const r = await fetch(API + "/slots?date=" + date);
  const data = await r.json();
  sc.innerHTML="";
  (data.slots||[]).forEach(slot=>{
    const el = document.createElement("button");
    el.className="opt slot"; el.textContent=slot.label;
    el.onclick = ()=>{ clearSel(sc); el.classList.add("sel"); st.slot=slot.start;
                       show("step-info", true); refreshSubmit(); };
    sc.appendChild(el);
  });
  if(!(data.slots||[]).length) sc.innerHTML='<div class="muted">Plus de créneau ce jour-là.</div>';
}
["f-name","f-email","f-phone"].forEach(id=>document.getElementById(id).addEventListener("input", refreshSubmit));

document.getElementById("submit-btn").onclick = async ()=>{
  const btn = document.getElementById("submit-btn"); btn.disabled=true; btn.textContent="Envoi…";
  document.getElementById("err").classList.add("hidden");
  const payload = { reason: st.reason, slot_start: st.slot,
    name: document.getElementById("f-name").value, email: document.getElementById("f-email").value,
    phone: document.getElementById("f-phone").value, message: document.getElementById("f-msg").value };
  try{
    const r = await fetch(API + "/submit", {method:"POST", headers:{"Content-Type":"application/json"},
                                            body: JSON.stringify(payload)});
    const d = await r.json();
    if(d.ok){
      document.getElementById("form-view").classList.add("hidden");
      document.getElementById("done-view").classList.remove("hidden");
      document.getElementById("done-msg").textContent =
        "Un email de confirmation vient de vous être envoyé" + (payload.phone ? ", ainsi qu'un SMS." : ".");
    } else {
      const e = document.getElementById("err"); e.textContent = d.error || "Erreur, réessayez.";
      e.classList.remove("hidden"); btn.disabled=false; btn.textContent="Confirmer le rendez-vous";
    }
  }catch(err){
    const e = document.getElementById("err"); e.textContent="Erreur réseau, réessayez.";
    e.classList.remove("hidden"); btn.disabled=false; btn.textContent="Confirmer le rendez-vous";
  }
};
init();
</script>
</body>
</html>""".replace("__FAVICON_LINK__", (f'<link rel="icon" href="{favicon}">' if favicon else "")) \
    .replace("__HEADER_BRAND__", header_brand) \
    .replace("__HEAD_CLASS__", head_class) \
    .replace("__HERO_IMG__", hero_img) \
    .replace("__WEBSITE_LINK__", website_link) \
    .replace("__DESCRIPTION__", description) \
    .replace("__LABEL__", label).replace("__COLOR__", color).replace("__SITE__", site_js)
