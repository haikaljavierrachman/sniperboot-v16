#!/usr/bin/env python3
"""Pastikan entri settings dari reset script: semua nilai target."""
import os
import sys

os.environ["DB_PATH"] = "/tmp/verify_reset3.db"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sniper import config, db  # noqa: E402

db.init()
assert float(db.get("paper_initial_usd")) == 100.0
assert float(db.get("paper_cash_usd")) == 100.0
assert float(db.get("buy_usd")) == 5.0
assert float(db.get("paper_gas_eth")) == 0.00005
assert float(db.get("paper_slippage_pct")) == 0.01
print("SETTING DEFAULTS dari init: SEMUA OK")
