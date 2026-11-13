#!/usr/bin/env bash
# verrou-origine-cloudflare.sh — n'autorise 80/443 QUE depuis les plages Cloudflare.
#
# Objectif : empêcher de contourner Cloudflare en tapant l'IP du serveur en direct.
# Généré le 2026-08-23 à partir de cloudflare.com/ips-v4 et ips-v6.
#
# TROIS GARDE-FOUS pour ne JAMAIS se couper l'accès au serveur :
#   1. SSH (port 22) reste ouvert depuis partout — on ne se verrouille pas dehors.
#   2. Les connexions déjà établies continuent (ESTABLISHED,RELATED).
#   3. On ne touche QUE 80 et 443 : tout le reste garde la politique ACCEPT.
#
# Réversible : bash verrou-origine-cloudflare.sh --annuler
set -e

annuler() {
  iptables  -F CF_LOCK 2>/dev/null || true
  ip6tables -F CF_LOCK 2>/dev/null || true
  iptables  -D INPUT -p tcp -m multiport --dports 80,443 -j CF_LOCK 2>/dev/null || true
  ip6tables -D INPUT -p tcp -m multiport --dports 80,443 -j CF_LOCK 2>/dev/null || true
  iptables  -X CF_LOCK 2>/dev/null || true
  ip6tables -X CF_LOCK 2>/dev/null || true
  echo "Verrou retiré : 80/443 de nouveau ouverts à tous."
  exit 0
}
[ "$1" = "--annuler" ] && annuler

# Chaîne dédiée CF_LOCK : isolée, donc facile à retirer sans toucher au reste.
iptables  -N CF_LOCK 2>/dev/null || iptables  -F CF_LOCK
ip6tables -N CF_LOCK 2>/dev/null || ip6tables -F CF_LOCK

# 1. connexions établies : elles passent, quoi qu'il arrive.
iptables  -A CF_LOCK -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
ip6tables -A CF_LOCK -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
# 2. loopback (nginx local, monitoring).
iptables  -A CF_LOCK -i lo -j ACCEPT
ip6tables -A CF_LOCK -i lo -j ACCEPT

# 3. les plages Cloudflare — les seules autorisées à ouvrir une NOUVELLE connexion 80/443.
iptables  -A CF_LOCK -s 173.245.48.0/20 -j ACCEPT
iptables  -A CF_LOCK -s 103.21.244.0/22 -j ACCEPT
iptables  -A CF_LOCK -s 103.22.200.0/22 -j ACCEPT
iptables  -A CF_LOCK -s 103.31.4.0/22 -j ACCEPT
iptables  -A CF_LOCK -s 141.101.64.0/18 -j ACCEPT
iptables  -A CF_LOCK -s 108.162.192.0/18 -j ACCEPT
iptables  -A CF_LOCK -s 190.93.240.0/20 -j ACCEPT
iptables  -A CF_LOCK -s 188.114.96.0/20 -j ACCEPT
iptables  -A CF_LOCK -s 197.234.240.0/22 -j ACCEPT
iptables  -A CF_LOCK -s 198.41.128.0/17 -j ACCEPT
iptables  -A CF_LOCK -s 162.158.0.0/15 -j ACCEPT
iptables  -A CF_LOCK -s 104.16.0.0/13 -j ACCEPT
iptables  -A CF_LOCK -s 104.24.0.0/14 -j ACCEPT
iptables  -A CF_LOCK -s 172.64.0.0/13 -j ACCEPT
ip6tables -A CF_LOCK -s 2400:cb00::/32 -j ACCEPT
ip6tables -A CF_LOCK -s 2606:4700::/32 -j ACCEPT
ip6tables -A CF_LOCK -s 2803:f800::/32 -j ACCEPT
ip6tables -A CF_LOCK -s 2405:b500::/32 -j ACCEPT
ip6tables -A CF_LOCK -s 2405:8100::/32 -j ACCEPT
ip6tables -A CF_LOCK -s 2a06:98c0::/29 -j ACCEPT

# 4. tout le reste vers 80/443 : refusé.
iptables  -A CF_LOCK -j DROP
ip6tables -A CF_LOCK -j DROP

# On branche la chaîne sur 80/443 uniquement (idempotent : on retire un doublon éventuel).
iptables  -D INPUT -p tcp -m multiport --dports 80,443 -j CF_LOCK 2>/dev/null || true
ip6tables -D INPUT -p tcp -m multiport --dports 80,443 -j CF_LOCK 2>/dev/null || true
iptables  -A INPUT -p tcp -m multiport --dports 80,443 -j CF_LOCK
ip6tables -A INPUT -p tcp -m multiport --dports 80,443 -j CF_LOCK

echo "Verrou posé : 80/443 réservés à Cloudflare. SSH et le reste intacts."
