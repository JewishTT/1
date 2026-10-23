from platform_model import build as pm
import json
root = pm.ROOT
model = pm.build_model(root)
from platform_model import evidence
ev = evidence.build_evidence(root, model)
print(len(ev['facts']))
print(ev['stats'])
