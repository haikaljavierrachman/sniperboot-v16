#!/usr/bin/env python3
"""Probe audit_contract langsung untuk beberapa CA dari log scanner."""
import sys
sys.path.insert(0, "/root/workspace/cipher/projects/hoodsniper_v16_gabungan")
from sniper.trader import Trader
from sniper.safety import audit_contract
from sniper import config

print("BLOCKSCOUT:", config.BLOCKSCOUT_API)
t = Trader()
for ca in sys.argv[1:]:
    print(ca, "→", audit_contract(t, ca))
