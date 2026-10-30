"""
Health check endpoint for Genesis Dashboard.
Checks: HTTP status, response time, SSL cert, sitemap, robots.txt for each site.
"""
import ssl
import socket
import requests
from datetime import datetime, timezone
from urllib.parse import urlparse


def check_site_health(url: str, timeout: int = 10) -> dict:
    """Full health check for a single site."""
    parsed = urlparse(url)
    domain = parsed.hostname
    result = {
        "url": url,
        "domain": domain,
        "online": False,
        "status_code": None,
        "response_time_ms": None,
        "ssl": {"valid": False, "expires": None, "days_remaining": None, "issuer": None},
        "sitemap": {"accessible": False, "url": f"{url}/sitemap.xml"},
        "robots_txt": {"accessible": False, "url": f"{url}/robots.txt"},
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }

    # 1. HTTP check + response time
    try:
        r = requests.get(url, timeout=timeout, allow_redirects=True)
        result["online"] = r.status_code < 500
        result["status_code"] = r.status_code
        result["response_time_ms"] = round(r.elapsed.total_seconds() * 1000)
    except requests.RequestException as e:
        result["error"] = str(e)[:200]
        return result

    # 2. SSL certificate check
    if parsed.scheme == "https":
        try:
            ctx = ssl.create_default_context()
            with ctx.wrap_socket(socket.socket(), server_hostname=domain) as s:
                s.settimeout(5)
                s.connect((domain, 443))
                cert = s.getpeercert()
                expires_str = cert.get("notAfter", "")
                expires = datetime.strptime(expires_str, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
                days_remaining = (expires - datetime.now(timezone.utc)).days
                issuer = dict(x[0] for x in cert.get("issuer", []))
                result["ssl"] = {
                    "valid": days_remaining > 0,
                    "expires": expires.isoformat(),
                    "days_remaining": days_remaining,
                    "issuer": issuer.get("organizationName", issuer.get("commonName", "Unknown")),
                }
        except Exception as e:
            result["ssl"]["error"] = str(e)[:200]

    # 3. Sitemap check
    try:
        sitemap_url = f"{url}/sitemap.xml"
        r = requests.get(sitemap_url, timeout=5)
        result["sitemap"]["accessible"] = r.status_code == 200 and "<?xml" in r.text[:200]
        if result["sitemap"]["accessible"]:
            # Count URLs in sitemap
            result["sitemap"]["url_count"] = r.text.count("<loc>")
    except Exception:
        pass

    # 4. robots.txt check
    try:
        robots_url = f"{url}/robots.txt"
        r = requests.get(robots_url, timeout=5)
        result["robots_txt"]["accessible"] = r.status_code == 200 and len(r.text) > 10
        if result["robots_txt"]["accessible"]:
            result["robots_txt"]["has_sitemap_ref"] = "sitemap" in r.text.lower()
            result["robots_txt"]["allows_all"] = "disallow: /" not in r.text.lower() or "disallow: /\n" not in r.text.lower()
    except Exception:
        pass

    return result


def check_all_sites(sites: list[dict]) -> list[dict]:
    """Check health for all configured sites."""
    results = []
    for site in sites:
        url = site.get("url")
        if not url:
            continue
        health = check_site_health(url)
        health["site_code"] = site.get("code", "")
        health["site_name"] = site.get("name", "")
        results.append(health)
    return results
