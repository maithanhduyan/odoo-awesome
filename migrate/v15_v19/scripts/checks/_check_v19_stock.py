"""Check V19 stock modules and tables."""
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from migrate.config import *
from migrate.migrator import OdooConnection

dst = OdooConnection(V19_URL, V19_DB, V19_USER, V19_PASSWORD, "v19")
dst.connect()

# Check if stock_account module is installed
modules = dst.search_read("ir.module.module",
    [["name", "in", ["stock_account", "stock_landed_costs", "stock"]]],
    ["name", "state"])
print("=== V19 stock-related modules ===")
for m in modules:
    print(f"  {m['name']}: {m['state']}")

# Check if SVL table exists via SQL
def run_sql(sql):
    result = subprocess.run(
        ["docker", "exec", "postgres", "psql", "-U", "odoo", "-d", "taya19_db", "-t", "-A", "-c", sql],
        capture_output=True, text=True, timeout=30)
    return result.stdout.strip()

svl_sql = "SELECT tablename FROM pg_tables WHERE tablename LIKE 'stock_valuation%'"
print(f"\nSVL tables: {run_sql(svl_sql)}")
print(f"V19 stock_quant rows: {run_sql('SELECT COUNT(*) FROM stock_quant')}")
print(f"V19 stock_move_line rows: {run_sql('SELECT COUNT(*) FROM stock_move_line')}")

# Check V19 stock.move.line count via ORM
v19_sml = dst.search_count("stock.move.line")
print(f"V19 stock.move.line (ORM): {v19_sml}")

# Check stock moves states
print(f"\nV19 stock.move state distribution:")
print(run_sql("SELECT state, COUNT(*) FROM stock_move GROUP BY state ORDER BY count DESC"))

# Check stock picking states
print(f"\nV19 stock.picking state distribution:")
print(run_sql("SELECT state, COUNT(*) FROM stock_picking GROUP BY state ORDER BY count DESC"))

# Check if quants should be auto-generated
print(f"\nV19 stock_quant columns:")
print(run_sql("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='stock_quant' ORDER BY ordinal_position"))
