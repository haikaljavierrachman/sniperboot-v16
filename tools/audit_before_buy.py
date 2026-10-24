#!/usr/bin/env python3
"""Saring "audit: kontrak AKAN DIBELI" → laporan audit lengkap + keputusan beli."""
import sys
from pathlib import Path
sys.path.insert(0, "/root/workspace/cipher/projects/hoodsniper_v16_gabungan")
from sniper.trader import Trader
from sniper.safety import audit_contract

if len(sys.argv) != 2:
    print("pakai: python3 tools/audit_before_buy.py <contract_address>")
    sys.exit(1)

trader = Trader()
ok, msg = audit_contract(trader, sys.argv[1])
print("AUDITsummary:")
print(f"  OK={ok} | {msg}")
sys.exit(0 if ok else 2)
