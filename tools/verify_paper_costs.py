#!/usr/bin/env python3
"""Verifikasi jalur listener + reset kas (DB temporari, bukan produksi)."""
import os
import sys
import tempfile

_tmpdb = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmpdb.close()
os.environ["DB_PATH"] = _tmpdb.name
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sniper import config, db, dexscreener as dx  # noqa: E402

db.init()
pair = {"priceUsd": "0.001", "priceNative": "0.0005"}  # eth_usd fixture = 2.0
eth_price = dx.eth_usd(pair)
buy_usd = db.get("buy_usd")
gas_eth = float(db.get("paper_gas_eth", float) or 0.00005)
gas_usd = gas_eth * eth_price if eth_price > 0 else 0.12
total = buy_usd + gas_usd
assert db.get_paper_cash() == 100.0
assert db.deduct_paper_cash(total)
print(f"buy_usd={buy_usd} gas_usd={gas_usd:.4f} total={total:.4f}")
print(f"sisa kas setelah beli: {db.get_paper_cash():.4f}")
assert abs(db.get_paper_cash() - (100.0 - total)) < 1e-9

slip = float(db.get("paper_slippage_pct", float) or 0.01)
gross = max(buy_usd * (1.0 - slip), 0.0)
net = max(gross - gas_usd, 0.0)
new_cash = db.add_paper_cash(net)
expect = 100.0 - total + net
print(f"sell 0%pnl: gross={gross:.4f} net={net:.4f} kas akhir={new_cash:.4f}")
assert abs(new_cash - expect) < 1e-9
print("VERIFIKASI OK — buy memotong modal+gas, sell mengembalikan "
      "gross(slip) - gas.")
