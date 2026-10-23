import re, sys, os
root = r'C:\Users\tim\Desktop\COGNITIVE\1'
txt = open(os.path.join(root, 'apps/shared/events/topics.py'), encoding='utf-8').read()
tops = re.findall(r'^\s*([A-Z][A-Z0-9_]+)\s*=\s*["\']([^"\']+)["\']', txt, re.M)
print('topic constants:', len(tops))
for n, v in tops:
    print(' ', n, '=', v)
