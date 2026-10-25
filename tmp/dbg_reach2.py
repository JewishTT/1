import json
m = json.load(open(r'C:\Users\tim\Desktop\COGNITIVE\1\docs\platform\platform-model.json', encoding='utf-8'))
edges = m['import_graph']['edges']
target = 'apps/acquisition/adapters/registry.py'
print('importers of registry:', [e['from'] for e in edges if e['to'] == target])
sched = 'apps/acquisition/dispatcher/scheduler.py'
print('importers of scheduler:', [e['from'] for e in edges if e['to'] == sched])
print('scheduler imports:', [e['to'] for e in edges if e['from'] == sched][:10])
print('total edges', len(edges))
