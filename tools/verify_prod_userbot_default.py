# Verifikasi: db.init() pada salinan DB produksi → setting userbot_enabled tampil
import os, sqlite3, shutil, sys
proj = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
shutil.copy(os.path.join(proj, "hoodsniper.db"), "/tmp/prod_copy_v66.db")
os.environ["DB_PATH"] = "/tmp/prod_copy_v66.db"
sys.path.insert(0, proj)
from sniper import db
db.init()
c = sqlite3.connect("/tmp/prod_copy_v66.db")
row = c.execute("SELECT value FROM settings WHERE key='userbot_enabled'").fetchone()
print("prod DB userbot_enabled after db.init() =", row)
assert row and row[0] == "0", "setting userbot_enabled harus '0'"
print("OK: prod DB sudah default userbot off")
