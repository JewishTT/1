# -*- coding: utf-8 -*-
"""Strip old 0.12 section from zero-layer doc before regeneration."""
import io

path = r'C:\Users\tim\Desktop\COGNITIVE\1\docs\architecture\donors\10-ZERO-LAYER.md'

with io.open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

cut = None
for i, l in enumerate(lines):
    if l.startswith(u'## 0.12 Clone Inventory'):
        cut = i
        break

if cut is None:
    print('0.12 section not found — nothing to strip')
else:
    with io.open(path, 'w', encoding='utf-8') as f:
        f.writelines(lines[:cut])
    print('Stripped from line', cut + 1)
