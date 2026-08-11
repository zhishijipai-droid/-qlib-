import sys, os
os.chdir(os.path.dirname(__file__))

from db import init_db, seed_data
init_db()
count = seed_data() or "OK"
print(f"Seed done, count={count}")

import json
from db import get_db
db = get_db()
rows = db.execute("SELECT id, name FROM strategies").fetchall()
for r in rows:
    print(f"  {r['id']}: {r['name']}")
db.close()
