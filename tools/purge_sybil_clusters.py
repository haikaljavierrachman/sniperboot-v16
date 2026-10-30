#!/usr/bin/env python3
"""CLI Tool: Deteksi & Bersihkan Klaster Wash-Trading Dev Bot (Sybil Guard).

Mencari koin yang dibeli serempak oleh >= 7 dompet insider dalam jendela <= 60 detik.
Menonaktifkan dompet sybil, memasukkan ke blacklist, dan membersihkan riwayat insider_buys.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sniper import db


def main():
    parser = argparse.ArgumentParser(description="Deteksi & Bersihkan Klaster Sybil Botnet")
    parser.add_argument("--dry-run", action="store_true", help="Hanya tampilkan temuan tanpa mutasi DB")
    parser.add_argument("--min-wallets", type=int, default=7, help="Minimal dompet unik serempak (default: 7)")
    parser.add_argument("--window-sec", type=int, default=60, help="Jendela waktu dalam detik (default: 60)")
    args = parser.parse_args()

    db.init()

    if args.dry_run:
        # Lakukan deteksi saja tanpa purge
        import time
        from collections import defaultdict
        query = "SELECT ca, wallet, ts, symbol FROM insider_buys WHERE wallet IS NOT NULL AND wallet <> '' ORDER BY ca, ts ASC"
        with db._lock, db._conn() as c:
            rows = c.execute(query).fetchall()
        ca_buys = defaultdict(list)
        for r in rows:
            ca_buys[r["ca"]].append((r["ts"], (r["wallet"] or "").strip().lower(), r["symbol"]))

        clusters = []
        all_sybil_wallets = set()
        for c_ca, buys in ca_buys.items():
            sym = buys[0][2] if buys else ""
            n = len(buys)
            for i in range(n):
                t0 = buys[i][0]
                w_set = {buys[i][1]}
                span_sec = 0
                for j in range(i + 1, n):
                    t1 = buys[j][0]
                    if t1 - t0 <= args.window_sec:
                        w_set.add(buys[j][1])
                        span_sec = t1 - t0
                    else:
                        break
                if len(w_set) >= args.min_wallets:
                    wallets_list = list(w_set)
                    clusters.append({
                        "ca": c_ca,
                        "symbol": sym,
                        "wallets": wallets_list,
                        "span_sec": span_sec,
                    })
                    all_sybil_wallets.update(wallets_list)
                    break

        print(f"🔍 [DRY RUN] Ditemukan {len(clusters)} klaster wash-trading serempak (>= {args.min_wallets} wallets dlm <= {args.window_sec}s):")
        for cl in clusters:
            print(f"  - {cl['symbol']:12} {cl['ca']} : {len(cl['wallets'])} dompet dalam {cl['span_sec']}s")
        print(f"\nTotal dompet sybil teridentifikasi: {len(all_sybil_wallets)} dompet.")
        return

    print(f"🚀 Menjalankan deteksi dan pembersihan klaster sybil (min_wallets={args.min_wallets}, window_sec={args.window_sec}s)...")
    clusters = db.detect_and_purge_sybil_clusters(min_wallets=args.min_wallets, window_sec=args.window_sec)
    print(f"✅ Sukses! Ditemukan dan dibersihkan {len(clusters)} klaster:")
    all_w = set()
    for cl in clusters:
        print(f"  - {cl['symbol']:12} {cl['ca']} : {len(cl['wallets'])} dompet dalam {cl['span_sec']}s")
        all_w.update(cl["wallets"])
    print(f"\nTotal dompet sybil yang diblokir & dibuang: {len(all_w)} dompet.")
    active_now = len(db.list_insiders(only_enabled=True))
    print(f"Total insider aktif tersisa (bersih): {active_now} dompet.")


if __name__ == "__main__":
    main()
