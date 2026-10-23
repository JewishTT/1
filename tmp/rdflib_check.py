with open(r'C:\Users\tim\Desktop\COGNITIVE\1\apps\shared\semantic\shacl.py', encoding='utf-8') as f:
    for i,l in enumerate(f,1):
        if 'rdflib' in l or 'pyshacl' in l.lower():
            print(i, l.rstrip())
            if i>90: break
