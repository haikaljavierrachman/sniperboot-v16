#!/usr/bin/env python3
"""Perkakas CLI Sinkronisasi & Pemantauan Koin Induk (Parent Shield).

Penggunaan:
    python3 tools/sync_parents.py           # Sinkronisasi GeckoTerminal + tampilkan daftar
    python3 tools/sync_parents.py --list    # Tampilkan daftar koin induk di DB tanpa sync
    python3 tools/sync_parents.py --check <CA> <SYMBOL> # Cek apakah sebuah CA/simbol dianggap klon
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sniper import clone_guard, db


def main():
    parser = argparse.ArgumentParser(description="Parent Shield Manager")
    parser.add_argument("--list", action="store_true", help="Hanya tampilkan daftar koin induk")
    parser.add_argument("--check", nargs=2, metavar=("CA", "SYMBOL"), help="Tes apakah token ini klon parasit")
    args = parser.parse_args()

    db.init()

    if args.check:
        ca, sym = args.check
        risk, reason = clone_guard.is_clone_risk(ca, symbol=sym)
        print(f"Hasil cek untuk {sym} ({ca}):")
        print(f"  Risiko Klon : {'🚨 YA (Ditolak)' if risk else '✅ TIDAK (Lolos)'}")
        print(f"  Alasan      : {reason}")
        return

    if not args.list:
        print("🔄 Menghubungkan ke GeckoTerminal Robinhood Chain...")
        count = clone_guard.sync_parent_tokens()
        print(f"✅ Sinkronisasi selesai: {count} pool dievaluasi.")

    parents = clone_guard.list_parent_tokens()
    print(f"\n👑 Daftar Koin Induk Terdaftar ({len(parents)} koin):")
    print(f"{'Simbol':<12} {'Mcap':<15} {'Liquidity':<15} {'Contract Address'}")
    print("-" * 75)
    for p in parents:
        print(f"{p['symbol']:<12} ${p['mcap']:>12,.0f} ${p['liq']:>12,.0f} {p['ca']}")


if __name__ == "__main__":
    main()
