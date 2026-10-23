p = r'C:\Users\tim\Desktop\COGNITIVE\1\platform_model\narrative.py'
s = open(p, encoding='utf-8').read()
s = s.replace('    counts = model["counts"]\n', '    counts = _counts(model)\n')
open(p, 'w', encoding='utf-8').write(s)
print('counts occurrences:', s.count('_counts(model)'))
