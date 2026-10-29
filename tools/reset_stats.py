#!/usr/bin/env python3
"""Reset baseline counter statistik Hoodsniper ke 0 tanpa menghapus riwayat DB.

Penggunaan:
    python3 tools/reset_stats.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sniper import db  # noqa: E402


def main():
    db.init()
    pos_id, call_id = db.reset_stats()
    print("✅ Statistik Hoodsniper berhasil direset ke 0:")
    print(f"   Baseline Position ID : #{pos_id} (posisi lama tetap tersimpan utuh di DB)")
    print(f"   Baseline Call ID     : #{call_id}")
    print(f"   Stats baru           : {db.stats()}")


if __name__ == "__main__":
    main()
