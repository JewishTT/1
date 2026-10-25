p = r'C:\Users\tim\Desktop\COGNITIVE\1\platform_model\narrative.py'
lines = open(p, encoding='utf-8').read().splitlines(keepends=True)
start = None
end = None
for i, l in enumerate(lines):
    if l.startswith('#: Verified inconsistencies between docs and code.'):
        start = i
    if start is not None and l.startswith('def _counts(model: dict) -> dict:'):
        end = i
        break
assert start is not None and end is not None, (start, end)
# keep the two blank lines before def _counts
new = lines[:start] + lines[end:]
open(p, 'w', encoding='utf-8').write(''.join(new))
print('removed', end - start, 'lines')
