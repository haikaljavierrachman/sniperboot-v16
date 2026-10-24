#!/usr/bin/env python3
"""Perbandingan latensi per request: r beruntun ke Blockscout."""
import sys, time
sys.path.insert(0, "/root/workspace/cipher/projects/hoodsniper_v16_gabungan")
from sniper import safety

ca = "0x0147cf81c296abd6ef50954a81204c557b33d359"
for i in range(5):
    t0 = time.time()
    try:
        r = safety._S.get(safety.config.BLOCKSCOUT_API + "/smart-contracts/" + ca, timeout=15)
        print(f"#{i} status={r.status_code} total={time.time()-t0:.2f}s")
    except Exception as e:
        print(f"#{i} ERR={e.__class__.__name__} total={time.time()-t0:.2f}s")
