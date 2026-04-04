"""Compare V15 installed modules vs V19 available modules."""
v15 = set()
with open('scripts/v15_installed.txt', encoding='utf-16') as f:
    for line in f:
        name = line.strip()
        if name:
            v15.add(name)

v19 = set()
with open('scripts/v19_all.txt', encoding='utf-16') as f:
    for line in f:
        name = line.strip()
        if name:
            v19.add(name)

found = v15 & v19
missing = v15 - v19

print(f"V15 installed: {len(v15)}")
print(f"V19 available: {len(v19)}")
print(f"Found in V19:  {len(found)}")
print(f"Missing in V19: {len(missing)}")
print("\n--- MISSING modules (V15 installed but not in V19) ---")
for m in sorted(missing):
    print(f"  {m}")
print("\n--- FOUND modules (can be installed on V19) ---")
for m in sorted(found):
    print(f"  {m}")
