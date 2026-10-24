#!/usr/bin/env python3
"""Reset dompet kas virtual paper trading & sinkronisasi setting biaya.

- paper_initial_usd = 100.0
- paper_cash_usd   = 100.0
- buy_usd          = 5.0
(Juga memastikan paper_gas_eth & paper_slippage_pct ada di tabel settings.)

Jalankan: python3 tools/reset_paper_wallet.py
(DB = hoodsniper.db sesuai config.DB_PATH.)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sniper import config, db  # noqa: E402


def main():
    db.init()  # idempotent: buat tabel/kolom + seed default yang belum ada
    db.reset_paper_cash(100.0)
    db.set_("buy_usd", "5.0")
    db.set_("paper_gas_eth", "0.00005")
    db.set_("paper_slippage_pct", "0.01")
    print("✅ Reset paper wallet selesai:")
    print(f"   paper_initial_usd  = {db.get('paper_initial_usd')}")
    print(f"   paper_cash_usd     = {db.get('paper_cash_usd')}")
    print(f"   buy_usd            = {db.get('buy_usd')}")
    print(f"   paper_gas_eth      = {db.get('paper_gas_eth')} ETH")
    print(f"   (~${float(db.get('paper_gas_eth')) * 3500:.2f} @ ETH ~$3500 — per swap L2)")
    print(f"   paper_slippage_pct = {db.get('paper_slippage_pct')}")


if __name__ == "__main__":
    main()
