"""Explore remaining V15 data for Phases 20-22."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from migrate.config import *
from migrate.migrator import OdooConnection, IDMap

src = OdooConnection(V15_URL, V15_DB, V15_USER, V15_PASSWORD, "v15")
src.connect()
dst = OdooConnection(V19_URL, V19_DB, V19_USER, V19_PASSWORD, "v19")
dst.connect()
id_map = IDMap()

# ── CRM ──────────────────────────────────────────────────────────────
print("=" * 60)
print("CRM")
print("=" * 60)

print("\n--- V15 crm.lead samples ---")
leads = src.search_read("crm.lead", [],
    ["name", "partner_id", "user_id", "team_id", "stage_id",
     "type", "expected_revenue", "probability", "date_deadline",
     "phone", "email_from", "description", "active", "priority"],
    limit=0)
for l in leads:
    print(f"  #{l['id']} name={l['name']} type={l['type']} "
          f"partner={l.get('partner_id')} stage={l.get('stage_id')} "
          f"team={l.get('team_id')} revenue={l.get('expected_revenue')}")

print("\n--- V15 crm.team ---")
teams = src.search_read("crm.team", [], ["name", "active"], limit=0)
for t in teams:
    print(f"  #{t['id']} {t['name']} active={t['active']}")

try:
    print("\n--- V19 crm.team ---")
    teams19 = dst.search_read("crm.team", [], ["name", "active"], limit=0)
    for t in teams19:
        print(f"  #{t['id']} {t['name']} active={t['active']}")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n--- V15 crm.stage ---")
stages = src.search_read("crm.stage", [], ["name", "sequence"], limit=0)
for s in stages:
    print(f"  #{s['id']} {s['name']} seq={s['sequence']}")

try:
    print("\n--- V19 crm.stage ---")
    stages19 = dst.search_read("crm.stage", [], ["name", "sequence"], limit=0)
    for s in stages19:
        print(f"  #{s['id']} {s['name']} seq={s['sequence']}")
except Exception as e:
    print(f"  ERROR: {e}")

# ── PROJECT ──────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("PROJECT")
print("=" * 60)

print("\n--- V15 project.project samples ---")
try:
    projs = src.search_read("project.project", [],
        ["name", "partner_id", "user_id", "date_start", "date",
         "active", "company_id", "label_tasks"],
        limit=0)
    for p in projs:
        print(f"  #{p['id']} name={p['name']} partner={p.get('partner_id')} "
              f"user={p.get('user_id')} active={p.get('active')}")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n--- V15 project.task samples ---")
try:
    tasks = src.search_read("project.task", [],
        ["name", "project_id", "user_ids", "stage_id", "date_deadline",
         "priority", "active", "partner_id", "kanban_state"],
        limit=0)
    for t in tasks:
        print(f"  #{t['id']} name={t['name']} proj={t.get('project_id')} "
              f"stage={t.get('stage_id')} prio={t.get('priority')}")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n--- V15 project.task.type ---")
try:
    tstages = src.search_read("project.task.type", [], ["name", "sequence"], limit=0)
    for s in tstages:
        print(f"  #{s['id']} {s['name']} seq={s['sequence']}")
except Exception as e:
    print(f"  ERROR: {e}")

try:
    print("\n--- V19 project.task.type ---")
    tstages19 = dst.search_read("project.task.type", [], ["name", "sequence"], limit=0)
    for s in tstages19:
        print(f"  #{s['id']} {s['name']} seq={s['sequence']}")
except Exception as e:
    print(f"  V19 project.task.type: {e}")

# Check if V19 has project module
try:
    v19_proj = dst.search_count("project.project")
    print(f"\nV19 project.project count: {v19_proj}")
except Exception as e:
    print(f"\nV19 project.project: NOT AVAILABLE - {e}")

# ── ATTACHMENTS ──────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("IR.ATTACHMENT")
print("=" * 60)

all_att = src.search_read("ir.attachment", [],
    ["res_model", "type", "file_size", "store_fname", "mimetype"], limit=0)

model_dist = {}
type_dist = {}
total_size = 0
for a in all_att:
    rm = a.get("res_model") or "(empty)"
    model_dist[rm] = model_dist.get(rm, 0) + 1
    tp = a.get("type") or "?"
    type_dist[tp] = type_dist.get(tp, 0) + 1
    total_size += a.get("file_size") or 0

print(f"\nTotal: {len(all_att)} attachments, {total_size/1024/1024:.1f} MB")

print("\n--- By res_model ---")
for rm, cnt in sorted(model_dist.items(), key=lambda x: -x[1]):
    print(f"  {rm}: {cnt}")

print("\n--- By type ---")
for tp, cnt in sorted(type_dist.items(), key=lambda x: -x[1]):
    print(f"  {tp}: {cnt}")

v19_att = dst.search_count("ir.attachment")
print(f"\nV19 existing ir.attachment: {v19_att}")

# ── MAIL.MESSAGE ─────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("MAIL.MESSAGE")
print("=" * 60)

# Quick count by model and type
msg_count = src.search_count("mail.message")
print(f"\nTotal V15 mail.message: {msg_count}")

# Sample of message types
msgs_sample = src.search_read("mail.message", [],
    ["model", "message_type", "subtype_id", "res_id"], limit=100)

msg_model_dist = {}
msg_type_dist = {}
for mg in msgs_sample:
    mdl = mg.get("model") or "(empty)"
    msg_model_dist[mdl] = msg_model_dist.get(mdl, 0) + 1
    mt = mg.get("message_type") or "?"
    msg_type_dist[mt] = msg_type_dist.get(mt, 0) + 1

print("\n--- Messages by model (sample 100) ---")
for mdl, cnt in sorted(msg_model_dist.items(), key=lambda x: -x[1]):
    print(f"  {mdl}: {cnt}")

print("\n--- Messages by type (sample 100) ---")
for mt, cnt in sorted(msg_type_dist.items(), key=lambda x: -x[1]):
    print(f"  {mt}: {cnt}")

# Check actual distribution with search_count by type
for mtype in ["notification", "comment", "email", "user_notification", "auto_comment"]:
    cnt = src.search_count("mail.message", [["message_type", "=", mtype]])
    if cnt > 0:
        print(f"  message_type={mtype}: {cnt}")

v19_msg = dst.search_count("mail.message")
print(f"\nV19 existing mail.message: {v19_msg}")
