"""Cek & migrasi scanner settings di DB (v16.2 anti-pucuk).

DB mengoverride SETTING_DEFAULTS setelah init pertama, jadi nilai lama
(interval 120, max_age 1440) harus dinaikkan sekali ini.
"""
import sqlite3
import sys

TARGETS = {
    "scanner_interval_sec": "15",
    "scanner_max_age_min": "15",
    "scanner_max_h1_pump": "150",
    "scanner_min_liq": "5000",
}

def main(db_path):
    c = sqlite3.connect(db_path)
    try:
        rows = dict(c.execute(
            "SELECT key,value FROM settings WHERE key LIKE 'scanner%'").fetchall())
    except Exception as e:
        print("tabel settings tidak ada — init pertama.belum jalan:", e)
        return
    for k, v in sorted(rows.items()):
        print(k, "=", v)
    changed = []
    for k, want in TARGETS.items():
        cur = rows.get(k, want)
        if str(cur) != want:
            c.execute("INSERT INTO settings(key,value) VALUES(?,?) "
                      "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                      (k, want))
            changed.append(f"{k}: {cur} -> {want}")
    c.commit()
    if changed:
        print("[migrasi] " + "; ".join(changed))
    else:
        print("[migrasi] tidak ada yang perlu diubah")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "hoodsniper.db")
