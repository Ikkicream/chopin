# Demande de délisting SURBL — leclient-roi.com

- Où : http://www.surbl.org/surbl-analysis → chercher `leclient-roi.com` → « Request delisting » (formulaire, réponse sous 24-72 h en général).
- Constaté le 2026-07-07 : `leclient-roi.com.multi.surbl.org` → 127.0.0.64 (liste ABUSE).
- En parallèle : ouvrir un ticket au support Maildoso (c'est leur infra d'envoi/warmup, ils ont l'habitude).

## Texte à coller dans le formulaire (EN)

Subject: Delisting request for leclient-roi.com (legitimate business domain)

Hello,

I am requesting the removal of leclient-roi.com from the SURBL ABUSE list.

leclient-roi.com is a secondary sending domain owned and operated by Le Client ROI,
a French B2B company (primary website: https://leclientroi.com — note that the
domain simply 301-redirects there, which is standard practice to protect the
primary domain's reputation, not a throwaway setup).

Facts about the domain:
- Registered on 2026-06-23 by our company; same ownership as leclientroi.com.
- DNS fully authenticated: SPF, DKIM (2048-bit) and a strict DMARC policy
  (p=reject; pct=100) are in place and passing.
- Email activity so far consists only of the mailbox warm-up service of our
  email infrastructure provider (Maildoso) and a handful of internal test
  messages to our own founder's address. No marketing or bulk email has been
  sent from this domain yet.
- All future mail will be low-volume, targeted French B2B correspondence with
  a working unsubscribe mechanism and a monitored reply address.

We believe the listing is a false positive triggered by the domain's young age
and its redirect to our primary site. We would appreciate a review and removal.

I am happy to provide any additional verification you may need.

Best regards,
Camille Afchain
Le Client ROI — https://leclientroi.com
contact@leclientroi.com

## Après le délisting

- Re-vérifier : `dig +short leclient-roi.com.multi.surbl.org` (vide = délisté).
- Relancer un mail-tester pour confirmer la disparition de URIBL_ABUSE_SURBL (−1.9 pts).
