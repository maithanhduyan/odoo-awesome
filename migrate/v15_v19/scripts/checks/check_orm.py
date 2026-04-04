"""Check ORM internal data differences between v15 and v19."""
import psycopg2

conn15 = psycopg2.connect(dbname='odoo', user='odoo', password='odoo', host='localhost')
conn19 = psycopg2.connect(dbname='odoo19', user='odoo', password='odoo', host='localhost')

for label, conn in [('v15', conn15), ('v19', conn19)]:
    cur = conn.cursor()
    cur.execute('SELECT count(*) FROM ir_model_data')
    print(f'{label} ir_model_data: {cur.fetchone()[0]}')
    cur.execute('SELECT count(*) FROM ir_model')
    print(f'{label} ir_model: {cur.fetchone()[0]}')
    cur.execute('SELECT count(*) FROM ir_model_fields')
    print(f'{label} ir_model_fields: {cur.fetchone()[0]}')
    cur.execute('SELECT count(*) FROM ir_ui_view')
    print(f'{label} ir_ui_view: {cur.fetchone()[0]}')

cur15 = conn15.cursor()
cur15.execute('SELECT count(*) FROM ir_translation')
print(f'\nv15 ir_translation rows: {cur15.fetchone()[0]}')

cur19 = conn19.cursor()
cur19.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='ir_module_module' AND data_type='jsonb'")
print(f'v19 ir_module_module jsonb cols: {[r[0] for r in cur19.fetchall()]}')

# Check what type of data is in jsonb fields
cur19.execute("SELECT shortdesc FROM ir_module_module WHERE shortdesc IS NOT NULL LIMIT 3")
for row in cur19.fetchall():
    print(f'  sample shortdesc jsonb: {row[0]}')

# Check v19 constraint/index differences
print('\n--- Foreign key constraints comparison ---')
for label, conn in [('v15', conn15), ('v19', conn19)]:
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM information_schema.table_constraints WHERE constraint_type='FOREIGN KEY' AND table_schema='public'")
    print(f'{label} foreign keys: {cur.fetchone()[0]}')
    cur.execute("SELECT count(*) FROM pg_indexes WHERE schemaname='public'")
    print(f'{label} indexes: {cur.fetchone()[0]}')

conn15.close()
conn19.close()
