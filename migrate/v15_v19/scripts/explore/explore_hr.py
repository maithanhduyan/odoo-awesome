"""Explore hr.employee fields in V15 and V19, plus sample data."""
import xmlrpc.client

pw = "TaYa@2022Pwd"

s15 = xmlrpc.client.ServerProxy("http://localhost:8069/xmlrpc/2/object")
u15 = xmlrpc.client.ServerProxy("http://localhost:8069/xmlrpc/2/common").authenticate(
    "taya_db", "tayafood@gmail.com", pw, {}
)
s19 = xmlrpc.client.ServerProxy("http://localhost:19069/xmlrpc/2/object")
u19 = xmlrpc.client.ServerProxy("http://localhost:19069/xmlrpc/2/common").authenticate(
    "taya19_db", "tayafood@gmail.com", pw, {}
)

# V15 fields
f15 = s15.execute_kw("taya_db", u15, pw, "hr.employee", "fields_get", [],
                      {"attributes": ["string", "type"]})
print("=== V15 hr.employee key fields ===")
keep_types = ("char", "many2one", "selection", "boolean", "date", "integer", "float", "text")
for k, v in sorted(f15.items()):
    if v["type"] in keep_types:
        print(f"  {k}: {v['type']} - {v['string']}")

print()

# V19 fields
f19 = s19.execute_kw("taya19_db", u19, pw, "hr.employee", "fields_get", [],
                      {"attributes": ["string", "type"]})
print("=== V19 hr.employee key fields ===")
for k, v in sorted(f19.items()):
    if v["type"] in keep_types:
        print(f"  {k}: {v['type']} - {v['string']}")

print()

# Common fields
common = set(f15.keys()) & set(f19.keys())
v15_only = set(f15.keys()) - set(f19.keys())
v19_only = set(f19.keys()) - set(f15.keys())
print(f"Common fields: {len(common)}")
print(f"V15-only: {sorted(v15_only)}")
print(f"V19-only important: {sorted([k for k in v19_only if not k.startswith('x_') and not k.startswith('message_')])}")

print()

# Sample V15 employees
print("=== V15 Employees ===")
emps = s15.execute_kw("taya_db", u15, pw, "hr.employee", "search_read", [[]],
                       {"fields": ["id", "name", "job_title", "department_id", "parent_id",
                                   "work_email", "work_phone", "user_id", "active",
                                   "identification_id", "birthday", "gender", "marital",
                                   "address_id", "address_home_id", "bank_account_id"],
                        "order": "id"})
for e in emps:
    print(e)

print()
# V19 employee
print("=== V19 Employees ===")
emps19 = s19.execute_kw("taya19_db", u19, pw, "hr.employee", "search_read", [[]],
                         {"fields": ["id", "name", "job_title", "department_id", "parent_id",
                                     "work_email", "work_phone", "user_id", "active",
                                     "identification_id", "birthday", "gender", "marital",
                                     "address_id", "private_street", "bank_account_id"],
                          "order": "id"})
for e in emps19:
    print(e)

# Job positions
print()
print("=== V15 hr.job ===")
jobs15 = s15.execute_kw("taya_db", u15, pw, "hr.job", "search_read", [[]],
                         {"fields": ["id", "name", "department_id"], "order": "id"})
for j in jobs15:
    print(j)

print()
print("=== V19 hr.job ===")
jobs19 = s19.execute_kw("taya19_db", u19, pw, "hr.job", "search_read", [[]],
                         {"fields": ["id", "name", "department_id"], "order": "id"})
for j in jobs19:
    print(j)
