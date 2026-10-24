"""Unit test antrean pending pool retry (Dexscreener indexing lag).

Firehose on-chain mendeteksi CA pool baru dalam hitungan detik, tapi
Dexscreener butuh 1-3 menit untuk mengindeks pair-nya. Tanpa antrean,
CA dibuang saat best_pair -> None danhilang selamanya.
"""
import asyncio
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# DB_PATH harus diset sebelum import sniper.config (dibaca saat import)
_tmpdb = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmpdb.close()
os.environ["DB_PATH"] = _tmpdb.name

from sniper import config, db  # noqa: E402
from sniper import scanner  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(f"{name}{' — ' + detail if detail and not cond else ''}")
    print(f"  {'OK' if cond else 'FAIL'} {name}"
          + (f" — {detail}" if detail and not cond else ""))


# ======================================================================
# 1) Init: tabel pending_pools dibuat, helper bisa dipanggil
# ======================================================================
print("\n=== 1. init & helper helper antrean ===")
db.init()
CA1 = "0X" + "a" * 40  # huruf besar → harus dinormalisasi ke lower
CA1L = CA1.lower()
CA2 = "0x" + "b" * 40

db.add_pending_pool(CA1)
pools = db.get_pending_pools(max_age_sec=600)
check("add_pending_pool: CA tercatat (dinormalisasi lower)",
      len(pools) == 1 and pools[0]["ca"] == CA1L, str(pools))
check("add_pending_pool: retries awal 0", pools[0]["retries"] == 0)
check("add_pending_pool: idempotent (INSERT OR IGNORE)",
      len(db.get_pending_pools()) == 1)

# ======================================================================
# 2) Simulasi siklus 1: Dexscreener belum punya pair → tetap pending, retry nambah
# ======================================================================
print("\n=== 2. cycle 1: best_pair None → tetap di antrean ===")

_orig_best_pair = scanner.dx.best_pair
_orig_fetch_profiles = scanner.fetch_profile_candidates
_orig_fetch_multipool = scanner.fetch_multipool_candidates
_orig_make_w3 = scanner._make_w3
_orig_market_ok = scanner.market_ok


class _FakePair:
    pass


def _fake_best_pair_none(ca):
    return None


def _fake_profiles():
    return []


def _fake_multipool(w3):
    return [CA1, CA2]  # 2 CA baru on-chain


def _fake_make_w3():
    return object()  # non-None → "factory on"


scanner.dx.best_pair = _fake_best_pair_none
scanner.fetch_profile_candidates = _fake_profiles
scanner.fetch_multipool_candidates = _fake_multipool
scanner._make_w3 = _fake_make_w3

config.SCAN_ENABLED = False  # non-relevant tapi jaga config

# factory on
config.SETTING_DEFAULTS.setdefault("scanner_factory_on", "1")
db.set_("scanner_factory_on", "1")

r1 = scanner.collect_and_rank()
check("cycle1: tidak ada kandidat lolos (belum ada pair)", r1 == [], str(r1))
pools = {p["ca"]: p for p in db.get_pending_pools()}
check("cycle1: kedua CA tetap di pending_pools",
      set(pools) == {CA1L, CA2}, str(sorted(pools)))
check("cycle1: retry CA1 bertambah jadi 1", pools.get(CA1L, {}).get("retries") == 1)
check("cycle1: retry CA2 bertambah jadi 1", pools.get(CA2, {}).get("retries") == 1)

# ======================================================================
# 3) Simulasi siklus 2: best_pair kembali pair → keluar dari antrean
# ======================================================================
print("\n=== 3. cycle 2: best_pair mengembalikan pair → diproses, keluar dari antrean ===")

fake_pair = {
    "pairAddress": "0x" + "c" * 40,
    "pairCreatedAt": int((asyncio.get_event_loop().time() if False else __import__("time").time() * 1000) - 60_000),
    "liquidity": {"usd": 5000.0},
    "priceUsd": "0.0001",
    "marketCap": 45000.0,
    "volume": {"h1": 30000.0, "m5": 500.0},
    "txns": {"h1": {"buys": 50, "sells": 30},
             "m5": {"buys": 10, "sells": 2}},
    "priceChange": {"m5": 12.0, "h1": 30.0},
}


def _fake_best_pair_ca1(ca):
    return fake_pair if ca == CA1L else None


scanner.dx.best_pair = _fake_best_pair_ca1

r2 = scanner.collect_and_rank()
check("cycle2: CA1 lolos (pair ditemukan)",
      len(r2) == 1 and r2[0]["ca"] == CA1L, str(r2))
check("cycle2: score ada", r2 and isinstance(r2[0]["score"], float))
pools = {p["ca"]: p for p in db.get_pending_pools()}
check("cycle2: CA1 dihapus dari pending (sudah idx)",
      CA1L not in pools, str(sorted(pools)))
check("cycle2: CA2 masih pending (best_pair masih None)", CA2 in pools)
check("cycle2: retry CA2 = 2 (sudah 2 siklus None)",
      pools.get(CA2, {}).get("retries") == 2,
      str(pools.get(CA2)))

# ======================================================================
# 4) Simulasi kedaluwarsa (> 600 detik) → prune_pending_poles
# ======================================================================
print("\n=== 4. kedaluwarsa → prune_pending_pools ===")

# Backdating: langsung UPDATE first_seen lewat db internal — cara pengujian
# aman yang tidak perlu sleep 10 menit.
import sqlite3  # di atas: di-track untuk kejelasan test ini saja

with db._lock, db._conn() as c:
    c.execute("UPDATE pending_pools SET first_seen = ? WHERE ca = ?",
              (int(__import__("time").time()) - 700, CA2))

# query dengan max_age 600 → harus tidak keliatan
left = db.get_pending_pools(max_age_sec=600)
check("get_pending_pools: kedaluwarsa tak dikembalikan oleh query",
      all(p["ca"] != CA2 for p in left), str(left))

db.prune_pending_pools(max_age_sec=600)
left = db.get_pending_pools(max_age_sec=10**9)
check("prune_pending_pools: baris kedaluwarsa dihapus",
      all(p["ca"] != CA2 for p in left), str(left))

# ======================================================================
# 5) Siklus 3: dup / seen_call → keluar dari antrean
# ======================================================================
print("\n=== 5. siklus 3: seen_call=True → keluar dari antrean ===")

scanner.fetch_multipool_candidates = _fake_multipool  # kembali dua CA, tapi
# CA1 sudah dicatat sebagai call → remove_pending, CA2 (ex-pending) juga seen?
# --- karena collect_and_rank tidak memanggil record_call sendiri
# (itu bagian listener.process_ca), kita record manual CA2 sebagai sudah
# diproses untuk mensimulasikan dup.
db.record_call(CA2, 1)  # source sintetis id=1

r3 = scanner.collect_and_rank()
# Yang diuji di siklus 3 murni ANTREAN (bukan dedup profil — profil Dexscreener
# memang bisa memunculkan CA yang worthy diproses ulang via pipeline listener):
#  - semua CA yang pernah di antrean sudah dibersihkan (expired / seen / removed)
#  - kedua CA memang dup (r3 boleh mengandung mereka, tapi hanya via jalur
#    profile — sama seperti sebelumnya, dulu keduanya lolos jalur profile di
#    collect_and_rank)
check("cycle3: antrean kosong (semua CA dibersihkan)",
      db.get_pending_pools(max_age_sec=10**9) == [],
      str(db.get_pending_pools(max_age_sec=10**9)))
check("cycle3: profil dedup → hanya 1 kandidat profil tersisa",
      scanner._last_stats["kandidat"] == 1,
      str(scanner._last_stats))
check("cycle3: 1 kandidat profil lolos walau dup via seen-pipeline (pipeline listener)",
      scanner._last_stats["lolos"] == 1,
      str(scanner._last_stats))
pools = db.get_pending_pools(600)
check("cycle3: antrean kosong (semua CA ter-unqueue)", pools == [], str(pools))

# ======================================================================
# 6) Restore mock & DB — jebakan lain tidak dikotamin
# ======================================================================
scanner.dx.best_pair = _orig_best_pair
scanner.fetch_profile_candidates = _orig_fetch_profiles
scanner.fetch_multipool_candidates = _orig_fetch_multipool
scanner._make_w3 = _orig_make_w3
scanner.market_ok = _orig_market_ok

print()
print(f"TOTAL: {len(PASS)} OK, {len(FAIL)} FAIL")
if FAIL:
    print(" FAIL:")
    for f in FAIL:
        print("   -", f)
    sys.exit(1)
