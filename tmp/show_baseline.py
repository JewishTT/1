import json
import pathlib

d = json.loads(
    pathlib.Path("specs/032-global-upgrade-execution/benchmarks/WP0-baseline-failures.json").read_text(encoding="utf-8")
)
for f in d["files"]:
    cats = {}
    for x in f["failures"]:
        cats[x["category"]] = cats.get(x["category"], 0) + 1
    print(f"{f['file']}  n={len(f['failures'])}  {cats}")
    for x in f["failures"]:
        print("    ", x["test"].split("::")[-1][:70], "|", x["error"], "|", x["location"], "|", x["message"][:110])
