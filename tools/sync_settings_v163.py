"""Sinkronisasi setting scanner v16.3 ke SQLite (jalankan sekali)."""
import sqlite3

KEYS = {
    "scanner_min_liq": "2000",
    "scanner_mcap_max": "45000",
    "scanner_max_age_min": "15",
}
DB = "hoodsniper.db"

con = sqlite3.connect(DB)
try:
    cols = [c[1] for c in con.execute("PRAGMA table_info(settings)").fetchall()]
    if "value" in cols:
        for k, v in KEYS.items():
            con.execute(
                "INSERT INTO settings(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, v))
    else:
        raise SystemExit(f"Skema settings tak dikenal: {cols}")
    con.commit()
    for k in KEYS:
        row = con.execute("SELECT value FROM settings WHERE key=?", (k,)).fetchone()
        print(k, "=", row[0] if row else None)
finally:
    con.close()
print("SYNC OK")
