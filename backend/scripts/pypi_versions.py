import json, sys, urllib.request
from datetime import datetime, timezone, timedelta

cutoff = datetime.now(timezone.utc) - timedelta(days=14)
for name in sys.argv[1:]:
    with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/json", timeout=15) as r:
        data = json.load(r)
    rows = []
    for ver, files in data["releases"].items():
        if not files or not ver.replace(".", "").isdigit():
            continue
        if all(f.get("yanked") for f in files):
            continue
        t = min(datetime.fromisoformat(f["upload_time_iso_8601"].replace("Z", "+00:00")) for f in files)
        rows.append((t, ver))
    rows.sort(reverse=True)
    print(name)
    for t, ver in rows[:6]:
        print(f"  {ver:12} {t.date()}  {'OK (older than 14 days)' if t < cutoff else 'too new'}")