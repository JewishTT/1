with open(r'C:\Users\tim\Desktop\COGNITIVE\1\apps\shared\semantic\shacl.py', encoding='utf-8') as f:
    content = f.read()
# find validate
idx = content.find('validate_with_shacl')
if idx >= 0:
    start = max(0, idx-200)
    end = min(len(content), idx+600)
    print(content[start:end])
else:
    print('not found')
    # look for try
    for i,l in enumerate(content.splitlines()):
        if 'try' in l and ('rdflib' in l or i<150):
            print(i,l)
            break
