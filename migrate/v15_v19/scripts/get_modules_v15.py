import xmlrpc.client

url = 'http://localhost:8069'
db = 'taya_db'
uid = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common').authenticate(db, 'admin', 'admin', {})
print(f'UID: {uid}')
models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
modules = models.execute_kw(db, uid, 'admin', 'ir.module.module', 'search_read',
    [[['state', '=', 'installed']]],
    {'fields': ['name', 'shortdesc', 'state'], 'order': 'name asc'})
print(f'Total installed: {len(modules)}')
for m in modules:
    print(f"  {m['name']:40s} {m['shortdesc']}")
