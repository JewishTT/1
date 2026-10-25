import json
m = json.load(open(r'C:\Users\tim\Desktop\COGNITIVE\1\docs\platform\platform-model.json', encoding='utf-8'))
mods = json.load(open(r'C:\Users\tim\Desktop\COGNITIVE\1\docs\platform\modules.jsonl', encoding='utf-8').read().splitlines()[0]) if False else None
# read maturity from modules.jsonl
rows = []
for line in open(r'C:\Users\tim\Desktop\COGNITIVE\1\docs\platform\modules.jsonl', encoding='utf-8'):
    line = line.strip()
    if not line:
        continue
    obj = json.loads(line)
    if obj.get('lang') != 'python':
        continue
    funcs = obj.get('functions', [])
    classes = obj.get('classes', [])
    methods = [x for c in classes for x in c.get('methods', [])]
    bodies = funcs + methods
    n = len(bodies)
    if n == 0 and obj['path'].rsplit('/', 1)[-1] != '__init__.py':
        rows.append((obj['path'], obj.get('loc', 0), obj.get('markers')))
for r in sorted(rows):
    print(r)
