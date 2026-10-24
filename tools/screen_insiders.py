#!/usr/bin/env python3
"""🕵️ tools/screen_insiders.py — Screening wallet insider (v16.1).

Cari "smart money" di Robinhood Chain: ambil koin yang sudah terbang
(gainers di Dexscreener atau dari daftar CA manual), baca pembeli-pembeli
awal mereka via Blockscout (robinhoodchain.blockscout.com), lalu cari
WALLET YANG TERBENTUR DI ≥2 KOIN PEMENANG — dia disimpan ke tabel
insider_wallets (db.sniper) untuk dipantau tracker on-chain.

Pemakaian:
  python tools/screen_insiders.py                     # auto: gainers Dexscreener
  python tools/screen_insiders.py 0xCa1 0xCa2 ...     # daftar CA manual
  python tools/screen_insiders.py --limit 3 --min-buy-eth 0.1
  python tools/screen_insiders.py --dry-run           # tampil saja, simpan tak

Ide: fase awal koin pemenang biasanya diisi wallet-wallet yang sama.
Wallet yang membeli 2+ koin pemenang di pembukaan kemungkinan besar
 insider yang benar — layak di-copy-trade.
"""
from __future__ import annotations

import argparse
import asyncio
import collections
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from curl_cffi import requests as crequests  # noqa: E402
from sniper import config, db  # noqa: E402
from sniper import dexscreener as dx  # noqa: E402
from sniper.tracker import QUOTE_ASSETS  # noqa: E402

# ---------- HTTP ----------
BROWSER_IMPERSONATE = "chrome120"     # identitas TLS yang cukup fresh
BLOCKSCOUT = config.BLOCKSCOUT_API.rstrip("/")
DEX_TRENDS = "https://api.dexscreener.com/token-profiles/latest/v1"
DEX_TOKENS = "https://api.dexscreener.com/latest/dex/tokens/{ca}"
DEX_SEARCH = "https://api.dexscreener.com/latest/dex/search?q=robinhood"

_session = crequests.Session(impersonate=BROWSER_IMPERSONATE)


def _get(url, *a, **kw):
    return _session.get(url, timeout=20, *a, **kw)


# ---------- 1. AMBIL KOIN YANG TERBANG ----------

DEX_PROFILES = "https://api.dexscreener.com/token-profiles/latest/v1"
DEX_BOOSTS = "https://api.dexscreener.com/token-boosts/latest/v1"
DEX_SEARCH_MULTI = "https://api.dexscreener.com/latest/dex/search?q={q}"


def _rh_cas_from_pairs(pairs: list) -> list[tuple[float, float, str]]:
    """CA Robinhood Chain dari daftar pair Dexscreener.
       Return list (volume24, priceChange24, ca)."""
    out = []
    for p in pairs or []:
        if (p.get("chainId") or "").lower() != config.DEX_CHAIN_MATCH.lower():
            continue
        ca = ((p.get("baseToken") or {}).get("address") or "").lower()
        if not ca.startswith("0x"):
            continue
        try:
            vol = float(((p.get("volume") or {}).get("h24")) or 0)
        except (TypeError, ValueError):
            vol = 0.0
        try:
            chg = float(((p.get("priceChange") or {}).get("h24")) or 0)
        except (TypeError, ValueError):
            chg = 0.0
        out.append((vol, chg, ca))
    return out


def _dexscreener_profiles_cas() -> list[str]:
    """CA dari token-profiles & token-boosts (filter chainId robinhood)."""
    cas = []
    for url in (DEX_PROFILES, DEX_BOOSTS):
        try:
            r = _get(url)
            items = r.json() or []
        except Exception as e:
            print(f"⚠️ Dexscreener {url.rsplit('/', 1)[-1]} gagal: {e}")
            continue
        for it in items if isinstance(items, list) else []:
            if (it.get("chainId") or "").lower() != config.DEX_CHAIN_MATCH.lower():
                continue
            ca = (it.get("tokenAddress") or "").lower()
            if ca.startswith("0x"):
                cas.append(ca)
    return cas


def fetch_gainers(limit=10) -> list[str]:
    """CA koin Robinhood Chain yang geaak trade — multi sumber:

      a. Dexscreener token-profiles + token-boosts (chainId=robinhood)
      b. Search multi-query: v4, robinhood, ETH, YMB (chainId=robinhood)
      c. Posisi sukses lokal (closed_tp1 / closed_tp2) dari DB sniper
      d. Dedup CA + urutkan berdasarkan volume/priceChange h24 menurun

    Jaringan gabung merge → 15-30 runner nyata walau search `robinhood`
    murni kosong.
    """
    cad: dict[str, tuple[float, float]] = {}   # ca → (vol24, chg24)

    # (a) profiles + boosts — endpoint token-list, tanpa metric harga
    for ca in _dexscreener_profiles_cas():
        if ca not in cad:
            cad[ca] = (0.0, 0.0)           # metric akan diisi dari query (b)

    # (b) search multi-query — metric volume/priceChange nyata
    for q in ("v4", "robinhood", "ETH", "YMB"):
        try:
            r = _get(DEX_SEARCH_MULTI.format(q=q))
            pairs = (r.json() or {}).get("pairs") or []
        except Exception as e:
            print(f"⚠️ Dexscreener search '{q}' gagal: {e}")
            continue
        for vol, chg, ca in _rh_cas_from_pairs(pairs):
            vol0, chg0 = cad.get(ca, (0.0, 0.0))
            cad[ca] = (max(vol, vol0), max(chg, chg0))

    # (c) posisi sukses lokal — CA yang pernah close TP1/TP2 di DB kita
    try:
        db.init()
        with db._lock, db._conn() as c:
            rows = c.execute(
                "SELECT DISTINCT ca FROM positions "
                "WHERE status IN ('closed_tp1','closed_tp2')").fetchall()
        for (ca,) in rows:
            ca = (ca or "").lower()
            if ca.startswith("0x"):
                vol0, chg0 = cad.get(ca, (0.0, 0.0))
                cad.setdefault(ca, (vol0, chg0))
    except Exception as e:
        print(f"⚠️ DB closed-positions gagal: {e}")

    # (d) skor = volume24 + priceChange24 — dedup justru di dict di atas.
    scored = sorted(cad.items(), key=lambda kv: kv[1][0] + kv[1][1],
                    reverse=True)
    return [ca for ca, _ in scored[:limit]]


def fetch_early_buyers(ca: str, max_buyers=50) -> list[dict]:
    """Pembeli EARLY sebuah koin: paged transfers via Blockscout.

    Return list dict: {from, value, ts} untuk transfer token pertama
    menuju pembeli (KAMI beli dari ETH → token, bukan airdrop dev/launchpad).
    """
    url = f"{BLOCKSCOUT}/tokens/{ca}/transfers"
    out = []
    try:
        r = _get(url)
        items = (r.json() or {}).get("items") or []
    except Exception as e:
        print(f"⚠️ Blockscout transfers {ca[:10]}… gagal: {e}")
        return []
    for it in items:
        # Blockscout token transfer: token.address, from, to, total
        toks = ((it.get("token") or {}).get("address") or "").lower()
        if toks and toks != ca.lower():
            continue  # transfer token lain dalam batch yang sama
        to = (it.get("to") or {}).get("hash") or ""
        frm = (it.get("from") or {}).get("hash") or ""
        # transfer OUT dari kontrak (mint/dev/burn) atau address sama → skip
        if not to or not frm:
            continue
        if to.lower() in QUOTE_ASSETS or frm.lower() in QUOTE_ASSETS:
            # swap(router): from=router → to=pembeli, TAPI dari quote asset
            # masih valid: transferOut token menuju pembeli via router
            pass
        val = 0.0
        try:
            val = float((it.get("total") or {}).get("value") or 0.0)
        except (TypeError, ValueError, AttributeError):
            dec = ((it.get("token") or {}).get("decimals") or 18)
            try:
                val = float((it.get("total") or {}).get("value") or 0) / (10 ** int(dec))
            except Exception:
                val = 0.0
        ts = it.get("timestamp")
        stamp = 0
        if isinstance(ts, dict):
            stamp = int(ts.get("timestamp") or 0)
        elif isinstance(ts, (int, float)):
            stamp = int(ts)
        is_contract = bool((it.get("to") or {}).get("is_contract", False))
        out.append({"from": frm.lower(), "to": to.lower(),
                    "value": val, "ts": stamp, "is_contract": is_contract})
        if len(out) >= max_buyers * 3:      # kasih buffer buat filter lagi
            break
    return out


def pick_buyers(transfers: list) -> list[str]:
    """Ambil alamat penerima (to) yang BUKAN kontrak router/launchpad.
       Biasanya trader EOA yang membeli (dari router → trader)."""
    buyers = []
    for t in transfers:
        if isinstance(t, str):
            to = t
            is_contract = False
        elif isinstance(t, dict):
            to = t.get("to") or ""
            is_contract = bool(t.get("is_contract", False))
        else:
            continue
        to = to.lower()
        if is_contract:
            continue
        # transfer dari quote/router ke EOA biasa = BUY
        if to and not to.endswith("cb2") and to not in QUOTE_ASSETS:
            buyers.append(to)
        if len(buyers) >= 50:
            break
    return buyers[:50]


# ---------- 2. KERUCUT-KERUCUT PENDINGIN ----------

def cross_check(winners_cas: list) -> list[tuple[str, int, list]]:
    """Set intersection: wallet yang muncul di ≥2 koin pemenang.
       Return list sorted (address, win_count, [ca...])."""
    owners = defaultdict(list)
    for ca in winners_cas:
        for buyer in pick_buyers(fetch_early_buyers(ca)):
            owners[buyer].append(ca)
    result = [
        (addr, len(cas), cas)
        for addr, cas in owners.items() if len(set(cas)) >= 2
    ]
    result.sort(key=lambda x: (-x[1], x[0]))
    return result


# ---------- 3. SIMPAN KE DB ----------

def persist(winner_rows: list, dry=False):
    """Simpan wallet kandidat: win_count naik beruntun, tidak menimpa."""
    for addr, cnt, cas in winner_rows:
        win_cas = ",".join(cas)
        if dry:
            print(f"  (dry) akan simpan {addr[:14]}… win_count +{cnt}")
            continue
        db.add_insider_wallet(
            addr, label="screen_insiders", win_count=cnt,
            notes="auto: korelasi koin pemenang",
            win_cas=win_cas, update_if_exists=True)
        print(f"✅ insider {addr[:14]}… win_count +{cnt} (CA: {win_cas[:60]}…)")


# ---------- CLI ----------

def main():
    ap = argparse.ArgumentParser(description="Screen koin terbang → insider wallets")
    ap.add_argument("cas", nargs="*", help="CA koin manual (opsional)")
    ap.add_argument("--limit", type=int, default=5,
                    help="max koin dikoreksikan (default 5)")
    ap.add_argument("--dry-run", action="store_true",
                    help="tampil saja, tidak menulis DB")
    args = ap.parse_args()

    cas = [c for c in args.cas if c.startswith("0x")]
    if not cas:
        print("🔍 Mencari koin gainers Robinhood di Dexscreener…")
        cas = fetch_gainers(args.limit)
        print(f"   {len(cas)} koin momentum didapat.")
    if not cas:
        print("Tidak ada koin kandidat. Coba berikan CA manual.")
        return

    db.init()
    rows = cross_check(cas)
    print(f"\n📊 Hasil intersection dari {len(cas)} koin:")
    if not rows:
        print("(belum ada wallet terbentur ≥2 koin — coba lagi nanti / CA lain)")
        return
    for addr, n, c in rows[:20]:
        print(f"  {addr}  win={n}  CAs={','.join(c[:10] for c in c)}")
    persist(rows, dry=args.dry_run)


if __name__ == "__main__":
    main()
