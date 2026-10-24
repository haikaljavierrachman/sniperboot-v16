"""Verifikasi manual market_ok & score_pair v16.3 (tanpa jaringan/web3).

Pagar anti-pucuk kini berbasis MARKET CAP, bukan persentase pump h1/m5
(koin baru lahir dengan harga mikroskopis; satu beli awal $50-$100
bikin % pool loncat +250..+390% secara alami — bukan pucuk).

Jalankan dari folder proyek: python3 tools/verify_market_ok_v162.py
"""
import os
import sys
import tempfile
import time

os.environ.setdefault("DB_PATH", os.path.join(tempfile.mkdtemp(), "test.db"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sniper import scanner, db  # noqa: E402

db.init()

ok = True
def check(name, cond, info=""):
    global ok
    print(("PASS" if cond else "FAIL"), name, info)
    if not cond:
        ok = False

NOW_MS = int(time.time() * 1000)

koin_baru = {
    "pairCreatedAt": NOW_MS - 5 * 60 * 1000,          # umur 5 menit
    "liquidity": {"usd": 8000},
    "priceChange": {"h1": 25.0, "m5": 12.0},          # momentum awal wajar
    "volume": {"h1": 300},                            # vol kecil — ok utk koin baru
    "txns": {"h1": {"buys": 8, "sells": 3},
             "m5": {"buys": 4, "sells": 1}},          # buy ratio m5 = 80%
}
mcrib = {  # kasus nyata: umur 40 mnt, h1 +803%, mcap $67k → HARUS DITOLAK
    "pairCreatedAt": NOW_MS - 40 * 60 * 1000,
    "liquidity": {"usd": 20000},
    "priceChange": {"h1": 803.0, "m5": 15.0},
    "volume": {"h1": 50000},
    "txns": {"h1": {"buys": 900, "sells": 200}, "m5": {"buys": 30, "sells": 5}},
    "marketCap": 67000.0,
}
# Kasus Dogzilla/Anna/MECHADOGE: h1 +250..+390% (beli awal $50-$100),
# tapi mcap masih $15k-$26k (lantai) → HARUS LOLOS
dogzilla = {
    "pairCreatedAt": NOW_MS - 4 * 60 * 1000,
    "liquidity": {"usd": 2800},                        # pool 1 ETH standar
    "priceChange": {"h1": 375.0, "m5": 88.0},          # alami utk koin baru
    "volume": {"h1": 150},
    "txns": {"h1": {"buys": 5, "sells": 1}, "m5": {"buys": 3, "sells": 0}},
    "marketCap": 26000.0,
}
pucuk_mcap = {  # mcap lewat pagar $45k → TOLAK walau umurnya baru
    "pairCreatedAt": NOW_MS - 3 * 60 * 1000,
    "liquidity": {"usd": 8000},
    "priceChange": {"h1": 90.0, "m5": 30.0},
    "volume": {"h1": 4000},
    "txns": {"m5": {"buys": 6, "sells": 2}},
    "marketCap": 52000.0,
}
pucuk_mcap_fdv = {**pucuk_mcap, "marketCap": None, "fdv": 61000.0}
sepi = {  # koin baru tapi belum ada aktivitas beli → TOLAK
    "pairCreatedAt": NOW_MS - 2 * 60 * 1000,
    "liquidity": {"usd": 6000},
    "priceChange": {"h1": 2.0, "m5": 0.0},
    "volume": {"h1": 0},
    "txns": {"h1": {"buys": 0, "sells": 0}, "m5": {"buys": 0, "sells": 0}},
}
lierendah = {**koin_baru, "liquidity": {"usd": 100}}
tanpa_umur_ok = {  # created=None → diperlakukan sebagai koin baru
    "liquidity": {"usd": 9000},
    "priceChange": {"h1": 40.0, "m5": 8.0},
    "volume": {"h1": 500},
    "txns": {"h1": {"buys": 10, "sells": 4}, "m5": {"buys": 3, "sells": 0}},
}

print("=== market_ok ===")
r = scanner.market_ok(koin_baru)
check("koin_baru lolos (ok_baru)", r == (True, "ok_baru"), str(r))
r = scanner.market_ok(mcrib)
check("McRib ditolak", r[0] is False and ("terlalu_tua" in r[1] or "pucuk" in r[1]), str(r))
r = scanner.market_ok(dogzilla)
check("Dogzilla (h1 +375%, mcap $26k) LOLOS", r == (True, "ok_baru"), str(r))
r = scanner.market_ok(pucuk_mcap)
check("mcap $52k > $45k ditolak (pucuk_mcap)", r[0] is False and "pucuk_mcap" in r[1], str(r))
r = scanner.market_ok(pucuk_mcap_fdv)
check("fallback fdv $61k ditolak (pucuk_mcap)", r[0] is False and "pucuk_mcap" in r[1], str(r))
# varian: tua TAPI mcap rendah → tetap ditolak umurnya
tua_lambat = {**koin_baru, "pairCreatedAt": NOW_MS - 120 * 60 * 1000,
              "priceChange": {"h1": 5.0, "m5": 1.0}, "marketCap": 20000.0}
r = scanner.market_ok(tua_lambat)
check("koin tua (120 mnt) ditolak", r[0] is False and "terlalu_tua" in r[1], str(r))
r = scanner.market_ok(sepi)
check("koin baru tanpa aktivitas beli ditolak", r[0] is False and "beli_sepi" in r[1], str(r))
r = scanner.market_ok(lierendah)
check("liq rendah ditolak", r[0] is False and "liq_rendah" in r[1], str(r))
r = scanner.market_ok(tanpa_umur_ok)
check("created=None → koin baru ok", r[0] is True, str(r))

print("=== score_pair ===")
baru_momentum = {**koin_baru}
paling_momentum = {**baru_momentum, "txns": {"h1": {"buys": 20, "sells": 2},
                                             "m5": {"buys": 10, "sells": 1}}}
s_baru = scanner.score_pair(baru_momentum)
s_punc = scanner.score_pair(paling_momentum)
check("bonus rentang manis m5 diterapkan", s_baru > 0.0, f"score={s_baru:.2f}")
check("buy ratio m5 >=70% memberi skor tertinggi", s_punc > s_baru,
      f"{s_punc:.2f} > {s_baru:.2f}")
datar = {**koin_baru, "priceChange": {"h1": 0.0, "m5": 0.0},
         "txns": {"h1": {"buys": 0, "sells": 0}, "m5": {"buys": 0, "sells": 0}}}
check("koin datar tanpa bonus", scanner.score_pair(datar) < s_baru,
      f"{scanner.score_pair(datar):.2f} < {s_baru:.2f}")

print("=== boundary mcap ===")
tepat = {**koin_baru, "marketCap": 45000.0}
r = scanner.market_ok(tepat)
check("mcap=$45,000 lolos (garis batas, tidak melewati)", r[0] is True, str(r))
sedikit = {**koin_baru, "marketCap": 45000.01}
r = scanner.market_ok(sedikit)
check("mcap=$45,000.01 ditolak", r[0] is False and "pucuk_mcap" in r[1], str(r))
tanpa_mcap = {**koin_baru}
_ = tanpa_umur_ok.pop("marketCap", None)
_ = tanpa_mcap.pop("marketCap", None)
r = scanner.market_ok(tanpa_mcap)
check("mcap kosong → tidak menolak", r[0] is True, str(r))

print()
if ok:
    print("SEMUA VERIFIKASI LULUS ✅")
else:
    print("ADA YANG GAGAL ❌")
    sys.exit(1)
