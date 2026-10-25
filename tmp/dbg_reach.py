import sys
sys.path.insert(0, r'C:\Users\tim\Desktop\COGNITIVE\1')
from platform_model import build as pm
m = pm.build_model(pm.ROOT)
edges = m['import_graph']['edges']
target = 'apps/acquisition/adapters/registry.py'
ins = [e['from'] for e in edges if e['to'] == target]
print('importers of', target, '=', ins)
sched = 'apps/acquisition/dispatcher/scheduler.py'
print('scheduler exists in modules:', any(x['path']==sched for x in m['python']['modules']))
print('importers of scheduler:', [e['from'] for e in edges if e['to']==sched])
print('does scheduler import registry?:', any(e['from']==sched and 'registry' in e['to'] for e in edges))
# any edge mentioning adapters.registry via
print('edges with via adapters.registry:', [(e['from'],e['to']) for e in edges if e.get('via')=='adapters.registry'][:5])
