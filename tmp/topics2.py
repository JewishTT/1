import re
txt = open(r'C:\Users\tim\Desktop\COGNITIVE\1\apps\shared\events\topics.py', encoding='utf-8').read()
pairs = re.findall(r'"([a-z][a-z0-9_.]+)"\s*:\s*"([a-z0-9_-]+)"', txt)
print('events:', len(pairs))
lanes = sorted(set(v for _, v in pairs))
print('lanes:', len(lanes), lanes)
