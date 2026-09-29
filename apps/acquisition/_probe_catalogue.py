"""One-shot check: does the catalogue load, and what does it actually contain?"""

from sources.catalogue import load_catalogue

defs, rej = load_catalogue()

print(f"ЗАГРУЖЕНО       : {len(defs)}")
print(f"ОТСЕЯНО         : {sum(len(v) for v in rej.values())}")
for code, names in sorted(rej.items()):
    print(f"   {code}: {len(names)}")
    for n in names[:3]:
        print(f"      - {n[:110]}")

keyless = [d for d in defs if not d.requires_key]
http = [d for d in defs if d.kind == "http"]
sysapp = [d for d in defs if d.kind == "system_app"]
paged = [d for d in defs if d.pagination.enabled]
identity = [d for d in defs if d.parser_is_identity]

print()
print(f"БЕЗ КЛЮЧА       : {len(keyless)}   <-- запускаются сразу")
print(f"http            : {len(http)}")
print(f"system_app      : {len(sysapp)}")
print(f"pagination ON   : {len(paged)} (inferred {sum(1 for d in paged if d.pagination.inferred)})")
print(f"contact inferred: {sum(1 for d in defs if d.contact_inferred)}")
print(f"kind inferred   : {sum(1 for d in defs if d.kind_inferred)}")
print(f"parser identity : {len(identity)}  <-- сырой payload")
print(f"enabled         : {sum(1 for d in defs if d.enabled)}")
print(f"требуют ключ    : {sum(1 for d in defs if d.requires_key)}")

d = next(x for x in defs if x.name == "certspotter_issuances")
print()
print("ПРОВЕРКА params -> URL (certspotter_issuances):")
print("  url:", d.tool["url"][:160])
print("  pagination:", d.pagination.to_dict())
print("  parser_is_identity:", d.parser_is_identity, "parser:", d.parser)

p = next(x for x in defs if x.pagination.enabled)
print()
print("ПРИМЕР страничного источника:", p.name)
print("  url:", p.tool["url"][:120])
print("  pagination:", p.pagination.to_dict())

print()
print("КАТЕГОРИИ:")
by_cat: dict[str, int] = {}
for x in defs:
    by_cat[x.category] = by_cat.get(x.category, 0) + 1
for cat in sorted(by_cat):
    print(f"   {cat:<34} {by_cat[cat]:>3}")
