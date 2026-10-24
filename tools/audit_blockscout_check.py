#!/usr/bin/env python3
"""Uji session Blockscout via curl_cffi (impersonate chrome120)."""
import sys
sys.path.insert(0, "/root/workspace/cipher/projects/hoodsniper_v16_gabungan")
from sniper import safety

for ca in sys.argv[1:]:
    try:
        r = safety._S.get(f"https://robinhoodchain.blockscout.com/api/v2/smart-contracts/{ca}", timeout=20)
        print(ca, "status:", r.status_code)
        d = r.json()
        print("  abi:", type(d.get("abi")), "| verified:", d.get("is_verified"))
    except Exception as e:
        print(ca, "ERR:", e.__class__.__name__, str(e)[:120])
