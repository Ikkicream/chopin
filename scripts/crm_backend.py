"""
crm_backend.py — Mini CRM per-site with DuckDB.
Each site gets its own .duckdb file.
"""

import duckdb
import uuid
import json
from datetime import datetime, timezone
from pathlib import Path

CRM_DIR = Path("/home/autoblog/genesis/data/crm")
CRM_DIR.mkdir(parents=True, exist_ok=True)


def get_db(site):
    """Get or create DuckDB connection for a site."""
    db_path = CRM_DIR / f"{site}.duckdb"
    conn = duckdb.connect(str(db_path))

    # Create tables if not exist
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id VARCHAR PRIMARY KEY,
            societe VARCHAR,
            nom VARCHAR,
            prenom VARCHAR,
            email VARCHAR,
            tel VARCHAR,
            source VARCHAR DEFAULT 'manual',
            statut VARCHAR DEFAULT 'nouveau',
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS societes (
            id VARCHAR PRIMARY KEY,
            nom VARCHAR,
            siret VARCHAR,
            secteur VARCHAR,
            taille VARCHAR,
            ville VARCHAR,
            site_web VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS interactions (
            id VARCHAR PRIMARY KEY,
            contact_id VARCHAR,
            type VARCHAR,
            contenu TEXT,
            agent VARCHAR DEFAULT 'manual',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    return conn


# ── Contacts CRUD ─────────────────────────────────────────────────────────────

def create_contact(site, data):
    conn = get_db(site)
    contact_id = str(uuid.uuid4())[:8]
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("""
        INSERT INTO contacts (id, societe, nom, prenom, email, tel, source, statut, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        contact_id,
        data.get("societe", ""),
        data.get("nom", ""),
        data.get("prenom", ""),
        data.get("email", ""),
        data.get("tel", ""),
        data.get("source", "manual"),
        data.get("statut", "nouveau"),
        data.get("notes", ""),
        now, now,
    ])
    # Auto-create interaction
    add_interaction(site, contact_id, "creation", f"Contact cr\u00e9\u00e9 (source: {data.get('source', 'manual')})")
    conn.close()
    return contact_id


def list_contacts(site, statut=None, date_from=None, date_to=None, limit=100):
    conn = get_db(site)
    query = "SELECT * FROM contacts WHERE 1=1"
    params = []
    if statut:
        query += " AND statut = ?"
        params.append(statut)
    if date_from:
        query += " AND created_at >= ?"
        params.append(date_from)
    if date_to:
        query += " AND created_at <= ?"
        params.append(date_to)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    result = conn.execute(query, params).fetchdf()
    conn.close()
    return result.to_dict(orient="records")


def get_contact(site, contact_id):
    conn = get_db(site)
    result = conn.execute("SELECT * FROM contacts WHERE id = ?", [contact_id]).fetchdf()
    interactions = conn.execute(
        "SELECT * FROM interactions WHERE contact_id = ? ORDER BY created_at DESC", [contact_id]
    ).fetchdf()
    conn.close()
    if result.empty:
        return None
    contact = result.to_dict(orient="records")[0]
    contact["interactions"] = interactions.to_dict(orient="records")
    return contact


def update_contact(site, contact_id, data):
    conn = get_db(site)
    fields = []
    values = []
    for k in ["societe", "nom", "prenom", "email", "tel", "statut", "notes"]:
        if k in data:
            fields.append(f"{k} = ?")
            values.append(data[k])
    if not fields:
        conn.close()
        return False
    fields.append("updated_at = ?")
    values.append(datetime.now(timezone.utc).isoformat())
    values.append(contact_id)
    conn.execute(f"UPDATE contacts SET {', '.join(fields)} WHERE id = ?", values)

    # Log status change
    if "statut" in data:
        add_interaction(site, contact_id, "statut", f"Statut \u2192 {data['statut']}")

    conn.close()
    return True


def delete_contact(site, contact_id):
    conn = get_db(site)
    conn.execute("DELETE FROM interactions WHERE contact_id = ?", [contact_id])
    conn.execute("DELETE FROM contacts WHERE id = ?", [contact_id])
    conn.close()
    return True


# ── Interactions ──────────────────────────────────────────────────────────────

def add_interaction(site, contact_id, interaction_type, contenu, agent="manual"):
    conn = get_db(site)
    interaction_id = str(uuid.uuid4())[:8]
    conn.execute("""
        INSERT INTO interactions (id, contact_id, type, contenu, agent, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, [interaction_id, contact_id, interaction_type, contenu, agent,
          datetime.now(timezone.utc).isoformat()])
    conn.close()
    return interaction_id


# ── Export ────────────────────────────────────────────────────────────────────

def export_csv(site):
    conn = get_db(site)
    result = conn.execute("SELECT * FROM contacts ORDER BY created_at DESC").fetchdf()
    conn.close()
    return result.to_csv(index=False)


# ── Stats ─────────────────────────────────────────────────────────────────────

def get_stats(site):
    conn = get_db(site)
    total = conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
    by_statut = conn.execute(
        "SELECT statut, COUNT(*) as cnt FROM contacts GROUP BY statut"
    ).fetchdf().to_dict(orient="records")
    recent = conn.execute(
        "SELECT * FROM contacts ORDER BY created_at DESC LIMIT 5"
    ).fetchdf().to_dict(orient="records")
    conn.close()
    return {"total": total, "by_statut": by_statut, "recent": recent}


# ── PRM (Pre-CRM: Emelia clicks/opens) ───────────────────────────────────────

PRM_DIR = Path("/home/autoblog/genesis/data/crm")

def get_prm_db(site):
    """Get PRM DuckDB connection."""
    db_path = PRM_DIR / f"prm_{site}.duckdb"
    conn = duckdb.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS prm_contacts (
            id VARCHAR PRIMARY KEY,
            email VARCHAR,
            firstName VARCHAR,
            lastName VARCHAR,
            company VARCHAR,
            campaign VARCHAR,
            action VARCHAR DEFAULT 'opened',
            action_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            transferred BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    return conn


def prm_add_contact(site, data):
    conn = get_prm_db(site)
    contact_id = str(uuid.uuid4())[:8]
    conn.execute("""
        INSERT INTO prm_contacts (id, email, firstName, lastName, company, campaign, action, action_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        contact_id,
        data.get("email", ""),
        data.get("firstName", ""),
        data.get("lastName", ""),
        data.get("company", ""),
        data.get("campaign", ""),
        data.get("action", "opened"),
        data.get("action_date", datetime.now(timezone.utc).isoformat()),
    ])
    conn.close()
    return contact_id


def prm_list(site, limit=200):
    conn = get_prm_db(site)
    result = conn.execute("SELECT * FROM prm_contacts WHERE transferred = FALSE ORDER BY created_at DESC LIMIT ?", [limit]).fetchdf()
    conn.close()
    return result.to_dict(orient="records")


def prm_transfer_to_crm(site, prm_id):
    """Transfer a PRM contact to the CRM."""
    conn = get_prm_db(site)
    result = conn.execute("SELECT * FROM prm_contacts WHERE id = ?", [prm_id]).fetchdf()
    if result.empty:
        conn.close()
        return None
    contact = result.to_dict(orient="records")[0]
    conn.execute("UPDATE prm_contacts SET transferred = TRUE WHERE id = ?", [prm_id])
    conn.close()

    # Create in CRM
    crm_id = create_contact(site, {
        "nom": contact.get("lastName", ""),
        "prenom": contact.get("firstName", ""),
        "email": contact.get("email", ""),
        "societe": contact.get("company", ""),
        "source": "emelia_" + contact.get("action", ""),
        "statut": "contacte",
        "notes": f"Transf\u00e9r\u00e9 depuis PRM. Campagne: {contact.get('campaign', '')}. Action: {contact.get('action', '')}",
    })
    return crm_id


def prm_delete(site, prm_id):
    conn = get_prm_db(site)
    conn.execute("DELETE FROM prm_contacts WHERE id = ?", [prm_id])
    conn.close()


def prm_stats(site):
    conn = get_prm_db(site)
    total = conn.execute("SELECT COUNT(*) FROM prm_contacts WHERE transferred = FALSE").fetchone()[0]
    by_action = conn.execute("SELECT action, COUNT(*) as cnt FROM prm_contacts WHERE transferred = FALSE GROUP BY action").fetchdf().to_dict(orient="records")
    conn.close()
    return {"total": total, "by_action": by_action}
