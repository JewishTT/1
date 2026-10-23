import json
a = json.load(open(r'C:\Users\tim\Desktop\COGNITIVE\1\docs\platform\architecture.json', encoding='utf-8'))
for s in a['spec_traceability']['specs']:
    print(f"{s['id']:45} tasks={s['tasks_checked']}/{s['tasks_total']:4} modules={s['module_count']}")
