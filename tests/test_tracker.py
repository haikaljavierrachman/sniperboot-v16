"""🧪 Uji INSIDER TRACKER v16.1 — tanpa jaringan & tanpa Web3 asli.

Semua fungsi murni parser/DB dibuktikan di sini:
  - extract_token_out      (exactInputSingle / exactInput / multicall)
  - is_buy_call            (tokenIn quote vs token lain)
  - CRUD insider_wallets   (add / get_active / toggle / update_if_exists)
  - screen_insiders        (cross-check intersection + persist)
  - _inspect_block         (jalur sinyal + guard non-insider + slippage)
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sniper import config, db            # noqa: E402
from sniper import tracker               # noqa: E402
import tools.screen_insiders as si       # noqa: E402


# =========================================================
# 1. PARSER CALLDATA ROUTER
# =========================================================

def _eis_calldata(token_in: str, token_out: str) -> str:
    """exactInputSingle((tokenIn,tokenOut,fee,recipient,...)) — potong ke
    bagian penting: selector + offset(32B) + tuple(tokenIn, tokenOut)."""
    sel = "0x414bf389"
    def pad(a):
        return a.lower().replace("0x", "").rjust(64, "0")
    offset = "0" * 62 + "20"   # offset params = 0x20 (encode ABI asli)
    return sel + offset + pad(token_in) + pad(token_out)


def test_extract_exact_input_single():
    tok_in, tok_out = tracker.WETH, "0x" + "c" * 40
    data = _eis_calldata(tok_in, tok_out)
    out = tracker.extract_token_out(data)
    assert out == tok_out.lower(), out
    print("PASS extract_token_out/exactInputSingle")


def test_extract_exact_input_single_reverse():
    """Swap JUAL: tokenOut = WETH (quote) → harus tetap tahu token ACTUAL."""
    tok_out, tok_in = tracker.WETH, "0x" + "d" * 40
    data = _eis_calldata(tok_in, tok_out)
    out = tracker.extract_token_out(data)
    assert out == tok_in.lower(), out
    print("PASS extract_token_out/exactInputSingle reverse (SELL)")


def test_extract_multicall_path():
    """multicall(bytes[]) dengan path ABI-encoded — parser harus menemukan
    token dari word 64-hex (alamat ada di 40-hex kanan word)."""
    sel = tracker.MULTICALL
    token_a = "0x" + "a" * 40
    token_b = "0x" + "b" * 40
    # satu word: address Edmonton — pad kanan (left-pad nol), ABI standar
    blob = "0" * 24 + token_a[2:] + "0" * 24 + token_b[2:]
    data = sel + "0" * 64 + blob
    cands = [t.lower() for t in tracker._tokens_from_path(data)]
    assert token_a.lower() in cands and token_b.lower() in cands, cands
    out = tracker.extract_token_out(data)
    assert out in {token_a.lower(), token_b.lower()}, out
    print("PASS extract_token_out/multicall path")


def test_extract_reject_quote_only():
    """Calldata yang hanya berisi alamat quote → None."""
    data = tracker.EXACT_INPUT_SINGLE + "0" * 64 + \
        tracker.WETH.lower().replace("0x", "").rjust(64, "0")
    out = tracker.extract_token_out(data)
    assert out is None, out
    print("PASS extract_token_out reject quote-only")


def test_is_buy_call():
    buy = _eis_calldata(tracker.WETH, "0x" + "c" * 40)
    sell = _eis_calldata("0x" + "c" * 40, tracker.WETH)
    assert tracker.is_buy_call(buy) is True
    assert tracker.is_buy_call(sell) is False
    print("PASS is_buy_call")


# =========================================================
# 2. CRUD DB insider_wallets (DB sementara, tidak menyentuh hoodsniper.db)
# =========================================================

def _fresh_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    old = config.DB_PATH
    config.DB_PATH = tmp.name
    return tmp.name, old


def test_insider_crud():
    path, old = _fresh_db()
    try:
        db.init()
        a = "0x" + "a" * 40
        db.add_insider_wallet(a.upper(), label="test", win_count=2,
                              notes="unit", win_cas="0xcaa,0xcab")
        assert a in db.get_active_insiders()

        # update_if_exists: win_count ditambah (bukan ditimpa)
        db.add_insider_wallet(a, win_count=3, win_cas="0xcac",
                              update_if_exists=True)
        rows = db.list_insiders()
        assert rows[0]["win_count"] == 5, rows

        # toggle
        assert db.toggle_insider(a) == 0
        assert a not in db.get_active_insiders()
        assert db.toggle_insider(a) == 1
        assert a in db.get_active_insiders()

        # INSERT OR IGNORE: tidak duplikat row, win_count tidak berubah
        db.add_insider_wallet(a, win_count=99)
        rows = db.list_insiders()
        assert len(rows) == 1 and rows[0]["win_count"] == 5, rows
        print("PASS insider_wallets CRUD")
    finally:
        os.unlink(path)
        config.DB_PATH = old


# =========================================================
# 3. screen_insiders — intersection + persist
# =========================================================

def test_cross_check_intersection():
    winners = ["0x" + "c" * 40, "0x" + "d" * 40]
    buyers_1 = ["0x" + "a" * 40, "0x" + "b" * 40]
    buyers_2 = ["0x" + "a" * 40, "0x" + "e" * 40]   # wallet 'a' kena 2x

    si.fetch_early_buyers = (lambda ca, max_buyers=50:
                             buyers_1 if ca == winners[0] else buyers_2)
    rows = si.cross_check(winners)
    assert len(rows) == 1, rows
    addr, cnt, cas = rows[0]
    assert addr == "0x" + "a" * 40
    assert cnt == 2
    assert set(cas) == set(winners)
    print("PASS screen_insiders cross_check intersection")


def test_screen_insiders_persist():
    path, old = _fresh_db()
    try:
        db.init()
        rows = [("0x" + "f" * 40, 3,
                 ["0x" + "c1" * 20, "0x" + "c2" * 20, "0x" + "c3" * 20])]
        si.persist(rows, dry=False)
        assert "0x" + "f" * 40 in db.get_active_insiders()

        rows2 = [("0x" + "f" * 40, 2,
                  ["0x" + "c4" * 20, "0x" + "c5" * 20])]
        si.persist(rows2, dry=False)
        row = db.list_insiders()[0]
        assert row["win_count"] == 5, row          # naik, bukan timpa
        assert row["win_cas"].count(",") == 4, row  # 3+2 CA
        print("PASS screen_insiders persist (update_if_exists)")
    finally:
        os.unlink(path)
        config.DB_PATH = old


# =========================================================
# 4. _inspect_block — jalur sinyal + guard
# =========================================================

class FakeW3:
    def __init__(self, txs):
        self._txs = txs
        self.eth = self
    def get_block(self, n, full_transactions=True):
        return {"number": n, "transactions": self._txs}


def _tx_from_calldata(frm, to, data_hex):
    return {"from": frm, "to": to,
            "input": bytes.fromhex(data_hex[2:])}


def test_inspect_block_sends_signal():
    path, old = _fresh_db()
    try:
        db.init()
        insider = "0x" + "a" * 40
        db.add_insider_wallet(insider, win_count=2)
        token_out = "0x" + "c" * 40
        tx = _tx_from_calldata(
            insider, tracker.SWAP_ROUTER02,
            _eis_calldata(tracker.WETH, token_out))

        sent = []
        async def fake_process(ca, insider_addr="", notify=None):
            sent.append((ca, insider_addr))

        orig_p, orig_pair = tracker.process_insider_buy, tracker.dx.best_pair
        tracker.process_insider_buy = fake_process
        tracker.dx.best_pair = lambda ca: {"priceChange": {"m5": 0.5}}
        try:
            got = asyncio.run(tracker._inspect_block(FakeW3([tx]), 123))
        finally:
            tracker.process_insider_buy, tracker.dx.best_pair = orig_p, orig_pair

        assert got == 1, got
        assert sent == [(token_out.lower(), insider)], sent
        print("PASS _inspect_block → process_insider_buy (alamat insider diteruskan)")
    finally:
        os.unlink(path)
        config.DB_PATH = old


def test_inspect_block_ignores_non_insider():
    path, old = _fresh_db()
    try:
        db.init()
        tx = _tx_from_calldata(
            "0x" + "9" * 40, tracker.SWAP_ROUTER02,
            _eis_calldata(tracker.WETH, "0x" + "c" * 40))
        sent = []
        orig = tracker.process_insider_buy
        tracker.process_insider_buy = (lambda ca, insider_addr="",
                                       notify=None: sent.append(ca))
        tracker.dx.best_pair_orig = tracker.dx.best_pair
        orig_pair = tracker.dx.best_pair
        tracker.dx.best_pair = lambda ca: {"priceChange": {"m5": 0.0}}
        try:
            got = asyncio.run(tracker._inspect_block(FakeW3([tx]), 1))
        finally:
            tracker.process_insider_buy = orig
            tracker.dx.best_pair = orig_pair
        assert got == 0 and sent == [], (got, sent)
        print("PASS _inspect_block ignore non-insider")
    finally:
        os.unlink(path)
        config.DB_PATH = old


def test_inspect_block_price_guard():
    """Harga sudah lari >5% dalam 5m → sinyal ditahan (slippage guard)."""
    path, old = _fresh_db()
    try:
        db.init()
        insider = "0x" + "a" * 40
        db.add_insider_wallet(insider, win_count=1)
        tx = _tx_from_calldata(
            insider, tracker.SWAP_ROUTER02,
            _eis_calldata(tracker.WETH, "0x" + "c" * 40))
        sent = []
        async def fake_process(ca, insider_addr="", notify=None):
            sent.append(ca)
        orig_p, orig_pair = tracker.process_insider_buy, tracker.dx.best_pair
        tracker.process_insider_buy = fake_process
        tracker.dx.best_pair = lambda ca: {"priceChange": {"m5": 12.0}}
        try:
            got = asyncio.run(tracker._inspect_block(FakeW3([tx]), 5))
        finally:
            tracker.process_insider_buy, tracker.dx.best_pair = orig_p, orig_pair
        assert got == 0 and sent == [], (got, sent)
        print("PASS _inspect_block slippage guard (m5 +12% → skip)")
    finally:
        os.unlink(path)
        config.DB_PATH = old


def test_inspect_block_sell_skipped():
    """Insider: SELL (tokenOut = WETH) → jangan dikirim ke pipa buy."""
    path, old = _fresh_db()
    try:
        db.init()
        insider = "0x" + "a" * 40
        db.add_insider_wallet(insider, win_count=1)
        tok_in = "0x" + "c" * 40
        tx = _tx_from_calldata(
            insider, tracker.SWAP_ROUTER02,
            _eis_calldata(tok_in, tracker.WETH))
        sent = []
        async def fake_process(ca, insider_addr="", notify=None):
            sent.append(ca)
        orig_p, orig_pair = tracker.process_insider_buy, tracker.dx.best_pair
        tracker.process_insider_buy = fake_process
        tracker.dx.best_pair = lambda ca: {"priceChange": {"m5": 0.0}}
        try:
            got = asyncio.run(tracker._inspect_block(FakeW3([tx]), 7))
        finally:
            tracker.process_insider_buy, tracker.dx.best_pair = orig_p, orig_pair
        assert got == 0 and sent == [], (got, sent)
        print("PASS _inspect_block SELL skip (tokenOut = quote)")
    finally:
        os.unlink(path)
        config.DB_PATH = old


if __name__ == "__main__":
    test_extract_exact_input_single()
    test_extract_exact_input_single_reverse()
    test_extract_multicall_path()
    test_extract_reject_quote_only()
    test_is_buy_call()
    test_insider_crud()
    test_cross_check_intersection()
    test_screen_insiders_persist()
    test_inspect_block_sends_signal()
    test_inspect_block_ignores_non_insider()
    test_inspect_block_price_guard()
    test_inspect_block_sell_skipped()
    print("ALL TRACKER TESTS PASSED ✅")
