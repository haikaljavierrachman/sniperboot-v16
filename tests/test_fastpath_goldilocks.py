"""Unit test saklar Mode Entry (MATA LLM vs FAST-PATH Goldilocks).

Cakupan:
1) toggle setting 'entry_mode' mata <-> fast (simulasi handler callback).
2) goldilocks_eval: umur pool < 30s / > 180s di-skip, 60s lolos.
3) rasio liq/mcap < 0.35 di-skip, >= 0.35 lolos.
4) safety dev > 3% di-skip (via _fastpath_gate).
5) slippage quoter > 15% di-skip (via _fastpath_gate).
6) mode='mata': fast-path tidak aktif — agent.decide_entry tetap dipanggil.
7) default settings Goldilocks masuk DB.

Jalankan: python3 tests/test_fastpath_goldilocks.py
(DB temporari — tidak menyentuh produksi.)
"""
import asyncio
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_tmpdb = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmpdb.close()
os.environ["DB_PATH"] = _tmpdb.name

from sniper import config, db          # noqa: E402
from sniper import listener, dexscreener as dx  # noqa: E402
from sniper.listener import goldilocks_eval, _fastpath_gate  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(
        f"{name}{' — ' + detail if detail and not cond else ''}")
    print(f"  {'OK' if cond else 'FAIL'} {name}"
          + (f" — {detail}" if detail and not cond else ""))


db.init()

NOW_MS = time.time() * 1000
CA = "0x" + "aa" * 20
SRC = {"id": 1, "name": "UNITTEST", "mcap_max": 50000}


def pair(age_s=60, liq=5000.0, mcap=11000.0, price_native="0.0005",
         price_usd="0.001", symbol="GD"):
    """Pair Dexscreener sintetis: liq/mcap = liq/mcap langsung."""
    return {"pairAddress": "0PAIR" + "0" * 16, "chainId": "robinhood",
            "priceUsd": price_usd, "priceNative": price_native,
            "labels": ["v3"], "pairCreatedAt": NOW_MS - age_s * 1000,
            "marketCap": mcap,
            "liquidity": {"usd": liq},
            "baseToken": {"symbol": symbol, "address": CA},
            "quoteToken": {"symbol": "ETH"}}


_notifications = []


async def fake_notify(text, buttons=None, **kw):
    _notifications.append(text)
    return text


class FakeW3:
    def to_wei(self, x, unit):
        return int(x * 10**18)


class FakeTrader:
    addr = "0x" + "11" * 40
    w3 = FakeW3()

    def erc20(self, addr_):
        raise AssertionError("tidak dipakai di test ini")

    def pool_fee(self, addr_):
        return 3000


class WotoW3:
    def to_wei(self, x, unit):
        return int(x * 10**18)


class Dec18ERC20:
    def __init__(self, addr_):
        pass

    class functions:
        @staticmethod
        def decimals():
            class F:
                def call(self):
                    return 18
            return F()


# =====================================================================
print("\n[1] toggle setting entry_mode (simulasi handler callback)")
db.set_("entry_mode", "fast")
check("toggle: mata -> fast", db.get("entry_mode", str) == "fast",
      db.get("entry_mode", str))
db.set_("entry_mode", "mata")
check("toggle: fast -> mata", db.get("entry_mode", str) == "mata",
      db.get("entry_mode", str))
check("default entry_mode = mata",
      config.SETTING_DEFAULTS.get("entry_mode") == "mata")


# =====================================================================
print("\n[2] umur pool Goldilocks (min 30s, maks 180s)")
db.set_("entry_mode", "fast")
ok, tag, m = goldilocks_eval(pair(age_s=10))
check("umur 10s (< 30s) → skip", not ok and tag.startswith("age_")
      and abs(m["pool_age"] - 10.0) < 3.0, f"tag={tag}")
ok, tag, m = goldilocks_eval(pair(age_s=300))
check("umur 300s (> 180s, koin basi) → skip", not ok
      and tag.startswith("age_") and abs(m["pool_age"] - 300.0) < 2,
      f"tag={tag}")
ok, tag, m = goldilocks_eval(pair(age_s=60))
check("umur 60s → lolos", ok and tag == "", f"tag={tag} m={m}")


# =====================================================================
print("\n[3] rasio liq/mcap Goldilocks (min 0.35)")
# liq 5000 / mcap 11000 = 0.4545 → sudah lolos di [2] umur 60s.
# di bawah buat rasio: liq 5000, mcap 16666.7 → ratio 0.30
p = dict(pair(age_s=60), marketCap=16666.7)
ok, tag, m = goldilocks_eval(p)
check("rasio 0.30 (< 0.35) → skip liq_ratio_rendah",
      not ok and tag == "liq_ratio_rendah", f"tag={tag} ratio={m.get('ratio')}")
p = dict(pair(age_s=60), marketCap=14000.0)   # 5000/14000 = 0.3571
ok, tag, m = goldilocks_eval(p)
check("rasio 0.357 (>= 0.35) → lolos", ok and tag == "",
      f"tag={tag} ratio={m.get('ratio')}")
# liq kecil: 3500 < min_liq 4000
p = dict(pair(age_s=60), liquidity={"usd": 3500.0}, marketCap=9000.0)
ok, tag, _ = goldilocks_eval(p)
check("liq $3.500 (< $4.000) → skip liq_rendah", not ok and tag == "liq_rendah",
      tag)
# mcap di luar jendela: 6000 < 7000 / 30000 > 28000
p = dict(pair(age_s=60), marketCap=6000.0)
ok, tag, _ = goldilocks_eval(p)
check("mcap $6.000 (< $7.000) → skip mcap_out_of_range",
      not ok and tag == "mcap_out_of_range", tag)
p = dict(pair(age_s=60), marketCap=30000.0)
ok, tag, _ = goldilocks_eval(p)
check("mcap $30.000 (> $28.000) → skip mcap_out_of_range",
      not ok and tag == "mcap_out_of_range", tag)


# =====================================================================
print("\n[4] safety dev > 3% → skip (via _fastpath_gate)")
_orig_safety_check = listener.safety.check
_orig_safety_dev = listener.safety.dev_pct
_orig_safety_top = listener.safety.top_holders_pct
_orig_trader = listener._trader

listener._trader = FakeTrader()
listener._notify = fake_notify
p_ok = pair(age_s=60, liq=5000.0, mcap=11000.0)

# 4a: check lolos, dev 2% → lolos (quoter OK biar gate sampai tamat)
listener.safety.check = lambda tr, ca, p: (True, "ok")
listener.safety.dev_pct = lambda tr, ca: 2.0
listener.safety.top_holders_pct = lambda tr, ca, ex, n=10: 10.0
_res = {}


class QuoterOkEarly(FakeTrader):
    def erc20(self, addr_):
        class E:
            class functions:
                @staticmethod
                def decimals():
                    class F:
                        def call(self):
                            return 18
                    return F()

                @staticmethod
                def totalSupply():
                    class G:
                        def call(self):
                            return 25_000_000 * 10**18
                    return G()
        return E()

    def quote_buy_tokens(self, ca, ptype, fee, wei_in, min_out=0, pool_id=None):
        return True, 5000 * 10**18, ""


listener._trader = QuoterOkEarly()
ok, tag, _ = asyncio.run(_fastpath_gate(CA, p_ok))
check("dev 2% (<= 3%) → lolos", ok and tag == "", f"tag={tag}")

# 4b: dev 5% (> 3% Goldilocks) → skip
listener.safety.dev_pct = lambda tr, ca: 5.0
ok, tag, _ = asyncio.run(_fastpath_gate(CA, p_ok))
check("dev 5% (> 3%) → skip dev_terlalu_besar",
      not ok and tag == "dev_terlalu_besar", tag)

# 4c: safety.check menolak (honeypot) → skip
listener.safety.dev_pct = lambda tr, ca: 0.0
listener.safety.check = lambda tr, ca, p: (False, "honeypot selector")
ok, tag, _ = asyncio.run(_fastpath_gate(CA, p_ok))
check("honeypot → skip dev_terlalu_besar (gate safety)",
      not ok and tag == "dev_terlalu_besar", tag)


# =====================================================================
print("\n[5] slippage quoter > 15% → skip (via _fastpath_gate)")
listener.safety.check = lambda tr, ca, p: (True, "ok")
listener.safety.dev_pct = lambda tr, ca: 0.0
listener.safety.top_holders_pct = lambda tr, ca, ex, n=10: 10.0

# harga layar 0.001 / native 0.0005 → eth_price 2 → buy $5 = 2.5 ETH →
# expected 5000 token; min_out 15% = 4250 token. quote 3000 < 4250 → slip.
class QuoterSlip(FakeTrader):
    def erc20(self, addr_):
        return Dec18ERC20(addr_)

    def quote_buy_tokens(self, ca, ptype, fee, wei_in, min_out=0, pool_id=None):
        return False, 0, "slippage_exceeded_onchain"


listener._trader = QuoterSlip()
ok, tag, _ = asyncio.run(_fastpath_gate(CA, p_ok))
check("quote < ambang 15% → skip slippage_besar",
      not ok and tag == "slippage_besar", tag)


class QuoterFail(FakeTrader):
    def erc20(self, addr_):
        return Dec18ERC20(addr_)

    def quote_buy_tokens(self, ca, ptype, fee, wei_in, min_out=0, pool_id=None):
        return False, 0, "v3_quoter_not_enough_liquidity:kosong"


listener._trader = QuoterFail()
ok, tag, _ = asyncio.run(_fastpath_gate(CA, p_ok))
check("quoter revert → skip quote_gagal",
      not ok and tag.startswith("quote_gagal:"), tag)

# quote OK: 5000 token → entry $5/5000 = 0.001 → mcap on-chain
# 0.001 × 25jt supply = $25.000 <= scanner_mcap_max 45k → LOLOS
class QuoterOk(FakeTrader):
    def __init__(self, supply=25_000_000):
        self.supply = supply

    def erc20(self, addr_):
        tr = self
        class E:
            class functions:
                @staticmethod
                def decimals():
                    class F:
                        def call(self):
                            return 18
                    return F()

                @staticmethod
                def totalSupply():
                    class G:
                        def call(self):
                            return tr.supply * 10**18
                    return G()
        return E()

    def quote_buy_tokens(self, ca, ptype, fee, wei_in, min_out=0, pool_id=None):
        # expected 5000 token, min_out 4250 → quote di atas ambang → OK
        return True, 5000 * 10**18, ""


listener._trader = QuoterOk()
ok, tag, metr = asyncio.run(_fastpath_gate(CA, p_ok))
check("quote OK + mcap on-chain $25.000 → lolos gate",
      ok and tag == "" and abs(metr.get("tokens_total", 0) - 5000) < 1,
      f"tag={tag} m={metr}")

# mcap on-chain melebihi batas: supply 200jt → 0.001 × 200jt = $200.000
listener._trader = QuoterOk(supply=200_000_000)
ok, tag, _ = asyncio.run(_fastpath_gate(CA, p_ok))
check("mcap on-chain $200.000 (> 45k) → skip mcap_onchain_pucuk",
      not ok and tag == "mcap_onchain_pucuk", tag)


# =====================================================================
print("\n[6] mode='mata' → fast-path TIDAK aktif, agent tetap dipanggil")
_agent_calls = []
_fast_notifs = []


def fake_agent_buy(*a, **k):
    _agent_calls.append(1)
    return {"action": "BUY", "conviction": 90, "size_mult": 1.0,
            "tp1": 0.5, "tp2": 1.0, "sl": -0.3,
            "reason": "mata menjawab", "risks": ""}


_orig_best = listener.dx.best_pair
_orig_agent = listener.agent.decide_entry
_orig_notify = listener._notify

db.set_("entry_mode", "mata")
db.set_("agent_on", "1")
db.set_("agent_dry_run", "1")

listener.dx.best_pair = lambda ca: p_ok
listener.safety.check = lambda tr, ca, p: (True, "ok")
listener.agent.decide_entry = fake_agent_buy
listener._trader = QuoterOk()
listener._notify = fake_notify


async def fake_notify_fast(text, buttons=None, **kw):
    _fast_notifs.append(text)
    return text

npos = len(db.open_positions())
st = asyncio.run(listener.process_ca(CA, SRC, None, "UNITTEST", allow_buy=True))
check("mode mata: agent.decide_entry TERPANGGIL", len(_agent_calls) == 1,
      f"calls={len(_agent_calls)}")
check("mode mata: bukan skip_fast / posisi terbuka (dry_run_simulated)",
      st == "dry_run_simulated" and len(db.open_positions()) == npos + 1, st)
check("mode mata: TIDAK ada notif FAST-PATH",
      all("FAST-PATH" not in t for t in _notifications),
      str(_notifications[-1])[:120])

# sebaliknya mode fast: agent TIDAK dipanggil (0 detik LLM)
listener.agent.decide_entry = fake_agent_buy   # tetap terpasang spy
listener._notify = fake_notify_fast
_calls_before = len(_agent_calls)
db.set_("entry_mode", "fast")
st = asyncio.run(listener.process_ca(
    "0x" + "bb" * 20, dict(SRC, id=2), None, "UNITTEST", allow_buy=True))
check("mode fast: agent.decide_entry TIDAK dipanggil (0 detik LLM)",
      len(_agent_calls) == _calls_before and st.startswith(("dry_run", "bought")),
      f"calls {_calls_before}->{len(_agent_calls)}, st={st}")
check("mode fast: notif FAST-PATH BUY terkirim",
      any("FAST-PATH BUY" in t for t in _fast_notifs), st)


# =====================================================================
print("\n[7] default settings Goldilocks masuk DB")
for k, exp in (("goldilocks_min_age_sec", 30.0),
               ("goldilocks_max_age_sec", 180.0),
               ("goldilocks_min_liq", 4000.0),
               ("goldilocks_min_liq_mcap_ratio", 0.35),
               ("goldilocks_max_mcap", 28000.0),
               ("goldilocks_min_mcap", 7000.0),
               ("goldilocks_max_dev_pct", 0.03),
               ("goldilocks_max_top10_pct", 0.25),
               ("goldilocks_max_slippage", 0.15),
               ("goldilocks_tp1", 0.35),
               ("goldilocks_tp2", 0.80)):
    check(f"DB {k} = {exp}", abs(db.get(k, float) - exp) < 1e-9,
          str(db.get(k, float)))

# =====================================================================
print()
print(f"TOTAL: {len(PASS)} OK, {len(FAIL)} FAIL")
if FAIL:
    print(" FAIL:")
    for f in FAIL:
        print("   -", f)
    sys.exit(1)
print("SEMUA TES LULUS.")
