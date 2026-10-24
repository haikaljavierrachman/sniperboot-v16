"""Sinkronisasi sekali-jalan: set scanner_max_per_hour = "0" di hoodsniper.db."""
import sqlite3
import os

db_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "hoodsniper.db",
)
if not os.path.exists(db_path) or os.path.getsize(db_path) == 0:
    db_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "tools", "hoodsniper.db",
    )
con = sqlite3.connect(db_path)
cur = con.cursor()
if cur.execute(
    "SELECT value FROM settings WHERE key='scanner_max_per_hour'"
).fetchone():
    cur.execute(
        "UPDATE settings SET value='0' WHERE key='scanner_max_per_hour'"
    )
else:
    cur.execute(
        "INSERT INTO settings(key,value) VALUES('scanner_max_per_hour','0')"
    )
con.commit()
print("OK:", cur.execute(
    "SELECT key,value FROM settings WHERE key='scanner_max_per_hour'"
).fetchall())
con.close()
