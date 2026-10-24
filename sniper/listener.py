"""Listener userbot: pantau SEMUA source di DB (multi-group, dinamis tanpa restart)."""
import asyncio
import re
import time
import traceback
from telethon import events, Button
from . import config, db, safety, agent, dexscreener as dx

CA_RE = re.compile(r"0x[a-fA-F0-9]{40}")

_trader = None
_notify = None


# ---------- format kartu keputusan Mata (rapi & konsisten) ----------
def _fmt_usd(v) -> str:
    """$48.200 — pemisah ribuan gaya Indonesia, tanpa desimal."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "$?"
    return "$" + f"{v:,.0f}".replace(",", ".")


def _fmt_liq(v) -> str:
    """Tampilkan likuiditas; pool v4 tanpa data Dexscreener → 'n/a'."""
    return "liq n/a (v4 on-chain)" if v is None else f"liq ${v:,.0f}"


def _fmt_pct(v) -> str:
    """+184,0% / -15,6% — desimal koma gaya Indonesia, selalu bertanda."""
    if v is None:
        return "?"
    try:
        return f"{float(v):+.1f}%".replace(".", ",")
    except (TypeError, ValueError):
        return "?"


def _fmt_age(pair) -> str:
    """Umur pair: '6 mnt' / '2,5 jam' / '3,1 hari' / '?' bila tak diketahui."""
    ts = pair.get("pairCreatedAt")
    if not ts:
        return "?"
    try:
        m = max(0, int((time.time() * 1000 - float(ts)) / 60000))
    except (TypeError, ValueError):
        return "?"
    if m < 60:
        return f"{m} mnt"
    if m < 1440:
        return f"{m / 60:.1f} jam".replace(".", ",")
    return f"{m / 1440:.1f} hari".replace(".", ",")


def _n(x) -> str:
    return str(int(x)) if x is not None else "?"


def _agent_card(pair, ca, src_name, decision, mode, min_conv=None) -> str:
    """Kartu keputusan Mata dengan tata letak tetap:

    SEMUA teks yang di-render ke Telegram lewat sini sudah disanitasi
    via agent.sanitize_text — teks bebas MATA tidak boleh membawa
    kontrol/zero-width-char (anti spam & anti injeksi tampilan).

    Layout kartu:
        <header per mode>
        `CA`
        📊 Mcap .. · Liq .. (..% mcap) · Umur ..
        📈 Harga m5 .. · h1 .. · B/S m5 ../.. · h1 ../..
        🧭 **Analisa** · conviction N
        • klausa alasan 1 (dipisah ';' dari prompt)
        • klausa alasan 2
        ⚠️ **Risiko:** ..
        🎯 **Rencana:** ..       (khusus mode LATIHAN)
        _(tidak dieksekusi ...)_ (khusus mode LATIHAN)

    mode: "SKIP" | "RAGU" | "LATIHAN". Fungsi murni (tanpa I/O) —
    bisa di-unit-test. Angka metrik dihitung dari pair, BUKAN dari
    teks LLM, jadi selalu hadir dan selalu akurat.
    """
    sym = (pair.get("baseToken") or {}).get("symbol", "?")
    mcap = dx.mcap_of(pair)
    sym = pair.get("baseToken", {}).get("symbol", "?")

    def _fmt_liq(v):
        return "liq n/a (v4 on-chain)" if v is None else f"liq ${v:,.0f}"

    liq = dx.liq_usd_or_none(pair)
    liq_line = _fmt_liq(liq)
    liq_pct = (liq / mcap * 100) if (liq is not None and mcap > 0) else 0.0
    chg = pair.get("priceChange") or {}
    txns = pair.get("txns") or {}
    tx5 = txns.get("m5") or {}
    tx1 = txns.get("h1") or {}
    conv = decision.get("conviction", "?")

    if mode == "LATIHAN":
        head = f"🧪 **MODE LATIHAN — MATA MAU BUY {sym}** _via {src_name}_"
    elif mode == "RAGU":
        head = f"👁 **MATA RAGU → SKIP — {sym}** _via {src_name}_"
    else:
        head = f"👁 **MATA SKIP — {sym}** _via {src_name}_"

    lines = [head, f"`{ca}`"]
    if mode == "RAGU" and min_conv is not None:
        lines.append(f"⚖️ Conviction {conv} — di bawah ambang BUY {min_conv:.0f}")
    lines.append(
        f"📊 Mcap {_fmt_usd(mcap)} · {_fmt_liq(liq)}"
        + (f" ({liq_pct:.0f}% mcap)" if liq is not None and mcap > 0 else "")
        + f" · Umur {_fmt_age(pair)}")
    lines.append(
        f"📈 Harga m5 {_fmt_pct(chg.get('m5'))} · h1 {_fmt_pct(chg.get('h1'))} · "
        f"B/S m5 {_n(tx5.get('buys'))}/{_n(tx5.get('sells'))} · "
        f"h1 {_n(tx1.get('buys'))}/{_n(tx1.get('sells'))}")
    lines.append(f"🧭 **Analisa** · conviction {conv}")
    clauses = [c.strip() for c in str(decision.get("reason") or "").split(";")]
    clauses = [c for c in clauses if c]
    if clauses:
        lines += [f"• {c}" for c in clauses]
    else:
        lines.append("• (tanpa alasan tertulis)")
    risks = str(decision.get("risks") or "").strip()
    if risks:
        lines.append(f"⚠️ **Risiko:** {risks}")
    if mode == "LATIHAN":
        size = f"{float(decision.get('size_mult') or 1.0):.2f}".replace(".", ",")
        lines.append(
            f"🎯 **Rencana:** size {size}x · "
            f"TP1 +{float(decision.get('tp1') or 0) * 100:.0f}% · "
            f"TP2 +{float(decision.get('tp2') or 0) * 100:.0f}% · "
            f"SL {float(decision.get('sl') or 0) * 100:.0f}%")
        lines.append("_(tidak dieksekusi — mode latihan/dry-run)_")
    return "\n".join(lines)


def topic_id(msg) -> int:
    r = msg.reply_to
    if r is not None and getattr(r, "forum_topic", False):
        return getattr(r, "reply_to_top_id", None) or r.reply_to_msg_id or 1
    return 1


def register(user_client=None, trader=None, notify=None):
    """Pasang handler userbot. user_client OPSIONAL:

    - user_client is None → userbot non-aktif (default v16.6): tidak
      memasang listener apa pun, sinyal 100% dipasok scanner factory
      on-chain & tracker insider. Tidak boleh raise.
    - user_client is not None → pasang handler sinyal grup seperti biasa.
    """
    global _trader, _notify
    _trader, _notify = trader, notify
    if user_client is None:
        print("[listener] userbot non-aktif; sinyal 100% dipasok dari "
              "scanner factory & tracker.")
        return

    @user_client.on(events.NewMessage())
    async def handler(event):
        try:
            src = db.match_source(event.chat_id, topic_id(event.message))
            if src is None:
                return
            await _handle(event, src)
        except Exception:
            traceback.print_exc()


async def _handle(event, src):
    if db.paused():
        return
    caller_id = event.sender_id
    caller_name = None
    try:
        sender = await event.get_sender()
        if sender:
            caller_name = getattr(sender, "username", None) or getattr(sender, "first_name", None)
    except Exception:
        pass
    if db.get("agent_blacklist", str) == "1" and db.is_blacklisted(caller_id):
        if CA_RE.search(event.raw_text or ""):
            print(f"[blacklist-skip] call dari {caller_name or caller_id} diabaikan (di-blacklist Mata)")
        return
    text = event.raw_text or ""
    for ca in _extract_ca_strict(text):
        await process_ca(ca, src, caller_id, caller_name)


# ---------- PIPA DATA KERAS: teks grup TIDAK diteruskan ke MATA ----------
# Hanya ALAMAT kontrak valid + metadata numerik yang lewat ke evaluasi.
# Narasi, promosi, ajakan, atau instruksi bebas dari pesan grup dianggap
# TEKS TAK-DIPERCAYA dan DIBUANG sebelum sampai ke prompt MATA (anti
# prompt-injection). Dipisah dari listener agar bisa di-unit-test.
NUMERIC_META_RE = re.compile(r"^-?\d+(?:\.\d+)?$")

def _trusted_meta_value(v, max_len=200):
    """Metadata hanya diterima bila numerik murni (angka/percent) ATAU
    anggota daftar putih operator (nama grup). String bebas lain → None."""
    if v is None:
        return None
    s = str(v).strip()
    if NUMERIC_META_RE.match(s):
        return s[:max_len]
    return None

def _extract_ca_strict(text) -> list:
    """Ekstrak contract address dengan validasi ketat:
    batas kata di kedua sisi (tidak ikut potongan alamat yang lebih panjang),
    dedupe mempertahankan urutan kemunculan pertama."""
    if not text:
        return []
    found = re.findall(r"(?<![0-9a-fA-Fx])(0x[a-fA-F0-9]{40})(?![0-9a-fA-F])", str(text))
    return list(dict.fromkeys(found))


# =====================================================================
#  ⚡ FAST-PATH GOLDILOCKS DEFENSIVE — evaluasi entry MURNI math/bytecode
#  (0 detik LLM). Toggle via panel 🧠 Otak (setting 'entry_mode').
#  Fungsi evaluasi murni (tanpa I/O) dipisah agar bisa di-unit-test;
#  benda I/O (safety, quoter on-chain, notif) ada di _fastpath_gate.
# =====================================================================
def goldilocks_eval(pair) -> tuple[bool, str, dict]:
    """Filter statistik Goldilocks dari data Dexscreener (murni math).

    Return (lolos, skip_tag, metrik). skip_tag dipakai untuk status
    'skip_fast:<tag>' (umur/liq/mcap/ratio). Safety dev/top10 & slippage
    quoter diverifikasi di _fastpath_gate (butuh I/O on-chain).
    """
    now_ms = time.time() * 1000
    min_age = float(db.get("goldilocks_min_age_sec", float) or 10)
    max_age = float(db.get("goldilocks_max_age_sec", float) or 180)
    min_liq = float(db.get("goldilocks_min_liq", float) or 4000.0)
    min_ratio = float(db.get("goldilocks_min_liq_mcap_ratio", float) or 0.35)
    max_mcap = float(db.get("goldilocks_max_mcap", float) or 35000.0)
    min_mcap = float(db.get("goldilocks_min_mcap", float) or 5000.0)

    # ---- a. umur pool (pairCreatedAt milidetik) ----
    created = pair.get("pairCreatedAt")
    try:
        pool_age = max(0.0, (now_ms - float(created)) / 1000.0) if created else None
    except (TypeError, ValueError):
        pool_age = None
    if pool_age is None:
        return False, "age_unknown", {"pool_age": None}
    if pool_age < min_age:
        return False, f"age_{pool_age:.0f}s", {"pool_age": pool_age}
    if pool_age > max_age:
        return False, f"age_{pool_age:.0f}s", {"pool_age": pool_age}

    # ---- b. likuiditas & mcap ----
    liq = dx.liq_usd_or_none(pair)
    mcap = dx.mcap_of(pair)
    metr = {"pool_age": pool_age, "liq": liq, "mcap": mcap,
            "ratio": (liq / mcap) if (liq and mcap > 0) else 0.0}
    if liq is None or liq < min_liq:
        return False, "liq_rendah", metr
    if mcap <= 0 or mcap < min_mcap or mcap > max_mcap:
        return False, "mcap_out_of_range", metr
    # rasio likuiditas/mcap: liku harus tebal dibanding kapitalisasi
    if metr["ratio"] < min_ratio:
        return False, "liq_ratio_rendah", metr
    return True, "", metr


async def _fastpath_gate(ca, pair) -> tuple[bool, str, dict]:
    """Gate lengkap fast-path (bagian I/O): safety dev/top10/honeypot +
    quote on-chain mcap guard. Return (lolos, skip_tag, metrik goldilocks).

    skip_tag:
      'dev_terlalu_besar'  — safety menolak (dev/top10/honeypot/fail-closed)
      'quote_gagal:<err>'  — quoter on-chain revert/gagal
      'slippage_besar'     — quote di bawah ambang slippage 15%
      'mcap_onchain_pucuk' — mcap hasil quote on-chain > scanner_mcap_max
    """
    # ---- c. safety guard (bytecode honeypot + dev + top10) ----
    ok, reason = await asyncio.to_thread(safety.check, _trader, ca, pair)
    if not ok:
        print(f"[fast-safety] {ca[:10]}: {reason}")
        return False, "dev_terlalu_besar", {}
    # batas dev/top10 ketat versi Goldilocks (rasio, bukan persen)
    max_dev = float(db.get("goldilocks_max_dev_pct", float) or 0.04)
    max_top = float(db.get("goldilocks_max_top10_pct", float) or 0.30)
    dev = safety.dev_pct(_trader, ca)          # persen (0-100)
    if dev and dev / 100.0 > max_dev:
        return False, "dev_terlalu_besar", {}
    exclude = {pair.get("pairAddress", ""), ca}
    top = safety.top_holders_pct(_trader, ca, exclude)  # persen (0-100)
    if top and top / 100.0 > max_top:
        return False, "top10_terlalu_besar", {}

    metr = {}
    ok_m, tag, metr = goldilocks_eval(pair)
    if not ok_m:  # data berubah sejak tahap pertama — pakai tag terakhir
        return False, tag, metr
    liq, mcap, pool_age = metr["liq"], metr["mcap"], metr["pool_age"]

    # ---- d. zero-gas on-chain quoter (slippage ≤ 25% + mcap on-chain) ----
    buy_usd = db.get("buy_usd")
    eth_price = dx.eth_usd(pair)
    eth_spent = buy_usd / eth_price if eth_price > 0 else 0
    ptype = dx.pool_type(pair)
    fee = 3000
    if ptype == "v3":
        try:
            fee = int(_trader.pool_fee(pair["pairAddress"]))
        except Exception:
            fee = 3000
    wei_in = _trader.w3.to_wei(eth_spent, "ether") if eth_spent > 0 else 0
    dec = 18
    try:
        dec = int(_trader.erc20(ca).functions.decimals().call())
    except Exception:
        dec = 18
    price_native = float(pair.get("priceNative") or 0)
    expected_tokens = (eth_spent / price_native) if price_native > 0 else 0
    max_slip = float(db.get("goldilocks_max_slippage", float) or 0.25)
    min_out_raw = int(expected_tokens * (1.0 - max_slip) * (10 ** dec)) \
        if expected_tokens > 0 else 0
    try:
        ok_q, amt_raw, err_reason = await asyncio.to_thread(
            _trader.quote_buy_tokens, ca, ptype, fee, wei_in,
            min_out_raw, pool_id=pair["pairAddress"])
    except Exception as e:
        ok_q, amt_raw, err_reason = False, 0, f"quoter_exception:{e}"
    if not ok_q or amt_raw <= 0:
        if err_reason == "slippage_exceeded_onchain":
            return False, "slippage_besar", metr
        return False, f"quote_gagal:{err_reason or 'quoter_gagal'}", metr

    tokens_total = amt_raw / (10 ** dec)
    entry_price_usd = (db.get("buy_usd") / tokens_total) if tokens_total > 0 else 0
    total_supply = None
    try:
        supply_raw = await asyncio.to_thread(_trader.erc20(ca).functions.totalSupply().call)
        total_supply = supply_raw / (10 ** dec)
    except Exception:
        total_supply = None
    if not total_supply or total_supply <= 0:
        pair_price = float(pair.get("priceUsd") or 0)
        total_supply = (mcap / pair_price) if pair_price > 0 else 1_000_000_000
    mcap_onchain = entry_price_usd * total_supply
    scanner_mcap_max = float(db.get("scanner_mcap_max", float) or 45000)
    if mcap_onchain > scanner_mcap_max:
        return False, "mcap_onchain_pucuk", metr
    metr.update({"tokens_total": tokens_total,
                 "entry_price_usd": entry_price_usd,
                 "mcap_onchain": mcap_onchain})
    return True, "", metr


async def process_ca(ca, src, caller_id, caller_name, allow_buy=True):
    """Proses SATU kandidat CA lewat pipa: filter → sosmed → safety → Mata → buy.

    Dipakai listener (dari pesan grup) maupun scanner (sniper/scanner.py).
    allow_buy=False = PAGAR KERAS: setelah lolos semua tahap, buy TIDAK
    dieksekusi lewat jalur mana pun (termasuk fallback rule-based saat Mata
    mati/gagal) — fungsi berhenti di status "no_buy_scanner". Mekanisme ini
    TETAP TERSEDIA, tapi di v16 gabungan scanner TIDAK memakainya: scanner
    memanggil allow_buy=True dan eksekusi diatur mode global (agent_dry_run
    dst.), persis seperti sinyal dari grup.

    Return string status singkat:
      "dup" | "paused" | "filtered:<alasan>" | "skip_agent" | "dry_run" |
      "no_buy_scanner" | "bought" | "buy_failed:<err>"
    """
    if db.paused():
        return "paused"
    if db.seen_call(ca):
        return "dup"
    db.record_call(ca, src["id"], caller_id, caller_name)

    pair = await asyncio.to_thread(dx.best_pair, ca)
    if not pair:
        print(f"[skip] {ca} tidak ketemu di chain '{config.DEX_CHAIN_MATCH}'")
        return "filtered:no_pair"

    mcap = dx.mcap_of(pair)
    liq = dx.liq_usd_or_none(pair)
    sym = pair.get("baseToken", {}).get("symbol", "?")
    ptype_dx = dx.pool_type(pair)

    # ---------- Duopoli Guard: Tolak pool v3 (sarang tick-trap 100% rug) ----------
    if db.get("scanner_ignore_v3", str) == "1" and src.get("name") == "SCANNER" and ptype_dx == "v3":
        return "filtered:v3_pool_disabled"

    # ---------- v4: likuiditas Dexscreener sering null ----------------
    # Jangan sampai filter min-liq salah menolak (atau rug monitor buta).
    # Bila null → baca likuiditas ON-CHAIN StateView.getLiquidity; kalau
    # on-chain 0 → tolak (pool kosong, kasus grok).
    if liq is None:
        onchain_liq = None
        if ptype_dx == "v4":
            try:
                from . import v4 as v4mod
                _w3 = _trader.w3 if _trader is not None else None
                onchain_liq = v4mod.liquidity(pair["pairAddress"], _w3)
            except Exception:
                onchain_liq = None
        if onchain_liq is None:
            print(f"[liq] {sym} liq Dexscreener null dan on-chain tak terbaca "
                  f"— pakai ambang 0 saja saat ini")  # fallthrough ke filter bawah
        elif onchain_liq <= 0:
            print(f"[skip] {sym} v4 liquidity 0 (pool kosong)")
            return "filtered:v4_pool_kosong"

    if mcap <= 0 or mcap > src["mcap_max"]:
        print(f"[skip] {sym} mcap ${mcap:,.0f} > limit ${src['mcap_max']:,.0f} ({src['name']})")
        return "filtered:mcap"
    if liq is not None and liq < db.get("min_liq_usd"):
        # Dexscreener tahu likuiditasnya dan rendah → tolak
        print(f"[skip] {sym} liq ${liq:,.0f} < min")
        return "filtered:liq"
    if liq is None:
        print(f"[filter] {sym} liq Dexscreener null — dipakai on-chain (v4) / diteruskan")
        # liq sudah terverifikasi via StateView di atas (bila v4); kalau
        # ptype bukan v4 dan null, anggap 0 saja untuk filter (perilaku lama).
        if ptype_dx != "v4" and dx.liq_usd(pair) < db.get("min_liq_usd"):
            print(f"[skip] {sym} liq ${dx.liq_usd(pair):,.0f} < min")
            return "filtered:liq"

    # ---------- 🌐 FILTER SOSMED (X / Web / TG / dll) ----------
    soc_ok, soc_reason = dx.social_ok(pair)
    if not soc_ok:
        print(f"[social-skip] {sym}: {soc_reason}")
        await _notify(f"🌐 **SKIP {sym}** _via {src['name']}_\n`{ca}`\n{soc_reason}")
        return "filtered:social"

    ok, reason = await asyncio.to_thread(safety.check, _trader, ca, pair)
    if not ok:
        print(f"[safety-skip] {sym}: {reason}")
        await _notify(f"🛡 **SKIP {sym}** _via {src['name']}_\n`{ca}`\n{reason}")
        return "filtered:safety"

    # ---------- ⚡ FAST-PATH GOLDILOCKS (entry_mode='fast', 0 detik LLM) ----
    # Evaluasi murni matematika/bytecode: umur pool → liq/mcap → safety →
    # quote on-chain (slippage ≤ 15%, mcap on-chain ≤ scanner_mcap_max).
    # Lolos semua gate → keputusan sintetis conviction 90 → eksekusi di
    # alur bawah (dry_run_simulated ATAU live buy) seperti biasa.
    entry_mode = db.get("entry_mode", str) or "mata"
    if entry_mode == "fast":
        ok_f, tag_f, metr_f = await _fastpath_gate(ca, pair)
        if not ok_f:
            print(f"[fast-skip] {sym}: {tag_f}")
            await _notify(
                f"⚡ **FAST-PATH SKIP {sym}** _via {src['name']}_\n"
                f"`{ca}`\nreason: {tag_f}")
            return f"skip_fast:{tag_f}"
        liq_f = metr_f.get("liq") or 0.0
        mcap_f = metr_f.get("mcap") or 0.0
        ratio_f = metr_f.get("ratio") or 0.0
        age_f = metr_f.get("pool_age") or 0.0
        tp1_f = float(db.get("goldilocks_tp1", float) or 0.35)
        tp2_f = float(db.get("goldilocks_tp2", float) or 0.80)
        decision = {
            "action": "BUY",
            "conviction": 90,
            "size_mult": 1.0,
            "tp1_x": tp1_f,
            "tp2_x": tp2_f,
            "sl_x": -0.30,
            # alias kompatibilitas pipa eksekusi lama (blok dry-run/live
            # membaca key tp1/tp2/sl)
            "tp1": tp1_f, "tp2": tp2_f, "sl": -0.30,
            "risks": "",
            "reason": (f"⚡ FAST-PATH Goldilocks: umur {age_f:.0f}s, "
                       f"liq ${liq_f:,.0f}, mcap ${mcap_f:,.0f}, "
                       f"ratio {ratio_f * 100:.1f}%, quote OK"),
        }
        db.log_decision(ca=ca, symbol=sym, role="fastpath", action="BUY",
                        conviction=90, size_mult=1.0,
                        reason=decision["reason"], risks="goldilocks_defensive")
        await _notify(
            f"⚡ **FAST-PATH BUY {sym}** _via {src['name']}_\n"
            f"`{ca}`\n📊 mcap ${mcap_f:,.0f} | liq ${liq_f:,.0f} "
            f"({ratio_f * 100:.1f}%) | umur pool {age_f:.0f}s\n"
            f"🎯 TP1 +{tp1_f * 100:.0f}% · TP2 +{tp2_f * 100:.0f}% · "
            f"SL -30% (conviction 90)\n_{decision['reason']}_")
    # ---------- 👁 MATA: keputusan entry oleh LLM (opsional) ----------
    elif db.get("agent_on", str) == "1" and config.LLM_API_KEY:
        decision = None
        try:
            decision = await asyncio.to_thread(
                agent.decide_entry, pair, ca, src, reason,
                {"id": caller_id, "name": caller_name,
                 "track_record": db.caller_stats(caller_id)})
        except Exception as e:
            print(f"[agent fail, fallback rule-based] {sym}: {e}")
    if (decision and decision.get("blacklist_caller") and caller_id
            and db.get("agent_blacklist", str) == "1"):
        if db.get("agent_dry_run", str) == "1":
            await _notify(
                f"🧪 **MODE LATIHAN — Mata MAU mem-blacklist {caller_name or caller_id}**\n"
                f"_{decision['reason']}_\n(tidak dieksekusi karena masih latihan)")
        else:
            db.add_blacklist(caller_id, caller_name, decision["reason"])
            await _notify(
                f"🚫 **MATA MEM-BLACKLIST caller {caller_name or caller_id}**\n"
                f"_{decision['reason']}_\ncall dia berikutnya auto-skip. Kelola di panel 🧠 Otak.")
    if decision and decision["action"] == "SKIP":
        await _notify(_agent_card(pair, ca, src["name"], decision, "SKIP"))
        return "skip_agent"
    if decision and decision["action"] == "BUY" and decision["conviction"] < db.get("agent_min_conviction"):
        await _notify(_agent_card(pair, ca, src["name"], decision, "RAGU",
                                  min_conv=db.get("agent_min_conviction")))
        return "skip_agent"
    # ---------- 📉 STALENESS GATE: harga sudah lari dari harga evaluasi? ----------
    # MATA butuh waktu berpikir; kalau harga sudah melonjak melewati ambang
    # drift (setting agent_max_drift, default 50%) sejak snapshot → BUY
    # dibatalkan (beli di pucuk / mengincar liquidity yang sedang ditarik).
    # SKIP dari MATA tidak lewat sini (sudah memutuskan tidak buy).
    if decision and decision["action"] == "BUY":
        initial_price = float(((pair.get("priceUsd") or 0)))
        try:
            fresh = await asyncio.to_thread(dx.best_pair, ca)
            fresh_price = float((fresh or {}).get("priceUsd") or 0) if fresh else 0.0
        except Exception:
            fresh_price = 0.0
        max_drift = float(db.get("agent_max_drift") or 0.50)
        if fresh_price > 0 and agent.check_staleness(initial_price, fresh_price, max_drift):
            await _notify(
                f"⏳ **MATA BUY {sym} DIBATALKAN — HARGA STALE** _via {src['name']}_\n"
                f"`{ca}`\n"
                f"harga saat evaluasi ${initial_price:.10f} → saat eksekusi ${fresh_price:.10f} "
                f"(drift {((fresh_price/initial_price-1)*100) if initial_price > 0 else 0:.1f}% "
                f"> {max_drift*100:.0f}%)\n"
                f"alasan: price_stale_drift")
            print(f"[staleness-skip] {sym}: harga sudah drift > {max_drift*100:.0f}% "
                  f"sejak MATA evaluasi — buy dibatalkan")
            return "skip_agent:price_stale_drift"
    if decision and db.get("agent_dry_run", str) == "1":
        # ---------- 🧪 VIRTUAL PAPER TRADING (mode LATIHAN) ----------
        # Tidak lagi berhenti di "dry_run": FAKTA SINYAL TETAP
        # PILIH KOIN INI — jadi buka posisi SIMULASI, agar TP1/TP2/SL/trail
        # engine monitor ikut menguji rencana trading (harga on-chain
        # & saldo wallet KETIDAKTERLIBATAN sama sekali).
        await _notify(_agent_card(pair, ca, src["name"], decision, "LATIHAN"))
        eth_price = dx.eth_usd(pair)
        buy_usd = (db.get("buy_usd") * decision["size_mult"]) if decision else db.get("buy_usd")
        eth_spent = buy_usd / eth_price if eth_price > 0 else 0.0003
        # ---------- 📣 ON-CHAIN QUOTE (paper entry akurat, v16.4) ----------
        # Harga layar Dexscreener cached 30-60s + spread statis TIDAK
        # mencerminkan chain: di on-chain harga pool sudah bergeser / liku
        # habis (revert). Hitung entry dari simulasi swap aktual (eth_call
        # Quoter) pada detik eksekusi. Bila quote revert → BATALKAN entry,
        # jangan catat profit palsu.
        ptype_dx = dx.pool_type(pair)
        fee_dx = 3000
        if ptype_dx == "v3":
            try:
                fee_dx = int(_trader.pool_fee(pair["pairAddress"]))
            except Exception:
                fee_dx = 3000
        wei_in = _trader.w3.to_wei(eth_spent, "ether") if eth_spent > 0 else 0
        # expected (harga layar) → ambang min_out untuk guard slippage
        dec = 18
        try:
            dec = int(_trader.erc20(ca).functions.decimals().call())
        except Exception:
            dec = 18
        price_native = float(pair.get("priceNative") or 0)
        expected_tokens = (eth_spent / price_native) if price_native > 0 else 0
        slippage_buy = db.get("buy_slippage")
        min_out_raw = int(expected_tokens * (1.0 - slippage_buy) * (10 ** dec)) \
            if expected_tokens > 0 else 0
        try:
            ok_q, amt_raw, err_reason = await asyncio.to_thread(
                _trader.quote_buy_tokens, ca, ptype_dx, fee_dx, wei_in,
                min_out_raw, pool_id=pair["pairAddress"])
        except Exception as e:
            ok_q, amt_raw, err_reason = False, 0, f"quoter_exception:{e}"
        if not ok_q or amt_raw <= 0:
            reason_line = err_reason or "quoter_gagal"
            await _notify(
                f"❌ **SIMULASI BUY GAGAL (On-Chain Revert)** via {src['name']}\n"
                f"{ca}\n"
                f"Alasan on-chain: {reason_line}\n"
                f"_(koin tidak dimasukkan ke posisi karena di chain asli "
                f"transaksi ini pasti revert/gagal)_")
            return "buy_failed:" + reason_line
        # entry efektif RIIL: hasil quote on-chain (termasuk price impact)
        tokens_total = amt_raw / (10 ** dec)
        entry_price_usd = (buy_usd / tokens_total) if tokens_total > 0 else 0
        if tokens_total <= 0 or entry_price_usd <= 0:
            await _notify(
                f"❌ **SIMULASI BUY GAGAL (On-Chain Revert)** via {src['name']}\n"
                f"{ca}\n"
                f"Alasan on-chain: quoter_output_kosong (token 0 dihitung)\n"
                f"_(koin tidak dimasukkan ke posisi karena di chain asli "
                f"transaksi ini pasti revert/gagal)_")
            return "buy_failed:quoter_output_kosong"
        # ---------- 🛡 MCAP GUARD REAL-TIME ON-CHAIN (Solusi B, v16.5) ----
        # Mcap Dexscreener cached 30-60s terlambat. Hitung mcap dari harga
        # entry quote on-chain × total supply on-chain; tolak bila sudah
        # melewati batas keras (dipompa sniper lain).
        total_supply_tokens = None
        try:
            # pakai kontrak ERC20 yang sudah dibuat untuk decimals di atas
            _erc20 = _trader.erc20(ca)
            supply_raw = await asyncio.to_thread(
                _erc20.functions.totalSupply().call)
            total_supply_tokens = supply_raw / (10 ** dec)
        except Exception:
            total_supply_tokens = None
        if not total_supply_tokens or total_supply_tokens <= 0:
            # fallback estimasi dari pair Dexscreener
            pair_mcap = float(pair.get("marketCap") or pair.get("fdv") or 0)
            pair_price = float(pair.get("priceUsd") or 0)
            total_supply_tokens = (pair_mcap / pair_price) \
                if pair_price > 0 else 1_000_000_000
        mcap_onchain = entry_price_usd * total_supply_tokens
        mcap_max = float(db.get("scanner_mcap_max", float)
                         or 0) or float(src.get("mcap_max") or 45000)
        if mcap_onchain > mcap_max:
            await _notify(
                f"❌ **SIMULASI BUY GAGAL (Mcap On-Chain Pucuk)** "
                f"via {src['name']}\n"
                f"{ca}\n"
                f"Alasan on-chain: mcap_onchain_pucuk "
                f"($ {mcap_onchain:,.0f} > batas $ {mcap_max:,.0f})\n"
                f"_(koin tidak dimasukkan ke posisi karena sudah dipompa "
                f"melebihi batas aman $45k)_")
            return "buy_failed:mcap_onchain_pucuk"
        pos = {"ca": ca.lower(), "symbol": sym,
               "pair_address": pair["pairAddress"], "chain_slug": pair["chainId"],
               "pool_type": dx.pool_type(pair), "fee": 3000,
               "entry_price_usd": entry_price_usd,
               "tokens_total": tokens_total, "tokens_left": tokens_total,
               "eth_spent": eth_spent, "usd_spent": buy_usd,
               "honeypot": 0, "source_name": src["name"],
               "caller_id": caller_id, "caller_name": caller_name,
               "buy_tx": "simulated_buy", "is_simulated": 1}
        buy_usd_final = buy_usd
        # Biaya nyata: gas L2 per swap + modal koin. Gas dipotong kas
        # virtual di samping modal, dicatat terpisah di notifikasi.
        gas_eth_buy = float(db.get("paper_gas_eth", float) or 0.00005)
        gas_usd = gas_eth_buy * eth_price if eth_price > 0 else 0.12
        total_buy_cost = buy_usd_final + gas_usd
        if not db.deduct_paper_cash(total_buy_cost):
            # kas virtual kurang → posisi simulasi TIDAK dibuka
            await _notify(
                f"🧪 **MODE LATIHAN — BUY {sym} DIBATALKAN** _via {src['name']}_\n"
                f"`{ca}`\n"
                f"saldo_virtual_kurang (kas ${db.get_paper_cash():.2f} < "
                f"${total_buy_cost:.2f} = modal ${buy_usd_final:.2f} + gas ${gas_usd:.2f}) "
                f"— kas virtual tidak cukup.")
            return (False, f"saldo_virtual_kurang (kas "
                           f"${db.get_paper_cash():.2f} < ${total_buy_cost:.2f})")
        db.open_position(**pos)
        try:
            pid = max(p["id"] for p in db.open_positions() if p["ca"] == pos["ca"] and p["is_simulated"])
            db.update_position(
                pid,
                tp1_x=float(decision.get("tp1") or db.get("tp1")),
                tp2_x=float(decision.get("tp2") or db.get("tp2")),
                sl_x=float(decision.get("sl") or db.get("sl")),
                peak_price=entry_price_usd)
        except (ValueError, KeyError):
            pid = None
        db.log_decision(**{"ca": ca, "symbol": sym, "role": "screener",
                           "action": "BUY_SIMULATED",
                           "conviction": decision.get("conviction", 0),
                           "size_mult": decision.get("size_mult", 1.0),
                           "reason": str(decision.get("reason") or ""),
                           "risks": str(decision.get("risks") or "")})
        chart = f"https://dexscreener.com/{pos['chain_slug']}/{pos['pair_address']}"
        btn_sell = ([Button.inline("📉 Sell 50%", f"sell:{pid}:50"),
                     Button.inline("🚨 Sell ALL", f"sell:{pid}:100")] if pid else [])
        sell_line = ""
        if pid:
            sell_line = (f"\n🎯 TP1 +{float(decision.get('tp1') or db.get('tp1'))*100:.0f}% · "
                         f"TP2 +{float(decision.get('tp2') or db.get('tp2'))*100:.0f}% · "
                         f"SL {float(decision.get('sl') or db.get('sl'))*100:.0f}% (SIMULASI aktif)")
        await _notify(
            f"🧪 **[SIMULASI] BUY {sym}**  _via {src['name']}_\n"
            f"`{pos['ca']}`\n"
            f"💰 mcap ${mcap:,.0f} | {_fmt_liq(liq)} | {pos['pool_type']}\n"
            f"paper masuk **${pos['usd_spent']:.2f}** ({pos['eth_spent']:.6f} ETH) → "
            f"{pos['tokens_total']:,.0f} {sym}\n"
            f"entry ${pos['entry_price_usd']:.10f} (on-chain quote){sell_line}"
            f"\n💵 Modal: **${buy_usd_final:.2f}** + Gas: **${gas_usd:.2f}**"
            f" (Total: **${total_buy_cost:.2f}**) | Sisa Kas: **${db.get_paper_cash():.2f}**"
            f"\n_(posisi virtual — engine monitor TP/SL aktif, TANPA swap on-chain)_",
            buttons=[btn_sell,
                     [Button.url("📊 Chart", chart)]] if btn_sell else
                     [[Button.url("📊 Chart", chart)]],
        )
        return "dry_run_simulated"

    # ---------- 🧪 PAGAR FALLBACK saat LATIHAN ----------
    # Mata NYALA tapi tidak menjawab (LLM error/timeout) → decision None.
    # Tanpa pagar ini, jalur fallback rule-based di bawah mencoba buy
    # beneran dan dry-run TIDAK menahannya — dry-run hanya menahan
    # KEPUTUSAN Mata, bukan ketiadaan keputusan. Selama latihan berlaku:
    # tidak ada keputusan = tidak ada buy. Di mode LIVE pagar ini tidak
    # berlaku — fallback rule-based memang perilaku yang diinginkan.
    if (decision is None and db.get("agent_on", str) == "1"
            and db.get("agent_dry_run", str) == "1"):
        await _notify(
            f"🧪 **MODE LATIHAN — Mata tidak menjawab untuk {sym}** _via {src['name']}_\n"
            f"`{ca}`\nLLM error/timeout — jalur fallback rule-based DITAHAN "
            f"selama mode latihan (tidak ada keputusan = tidak ada buy).")
        return "dry_run"

    # ---------- 🔭 PAGAR KERAS (mekanisme allow_buy=False) ----------
    # Titik ini adalah SATU-SATUNYA jalan menuju trader.buy di bawah. Kalau
    # allow_buy=False, fungsi berhenti di sini — berlaku juga saat
    # decision=None (Mata mati/gagal → fallback rule-based). Di v14 jalur ini
    # mengunci scanner secara permanen; di v16 gabungan scanner lewat dengan
    # allow_buy=True dan titik ini hanya tercapai bila ada pemanggil lain
    # yang sengaja meminta pagar ditutup.
    if not allow_buy:
        ai_line = ""
        if decision:
            ai_line = (f"\n👁 Mata: **{decision['action']}** (conviction {decision['conviction']})"
                       f"\n_{decision['reason']}_")
        if _notify:
            await _notify(
                f"🔭 **SCANNER (dry): {sym}** lolos semua filter{ai_line}\n"
                f"`{ca}`\n💰 mcap ${mcap:,.0f} | {_fmt_liq(liq)}\n"
                f"— buy TIDAK dieksekusi (allow_buy=False)")
        return "no_buy_scanner"

    usd = db.get("buy_usd") * decision["size_mult"] if decision else None
    try:
        pos = await asyncio.to_thread(_trader.buy, ca, pair, src["name"], usd)
    except Exception as e:
        await _notify(f"❌ Gagal buy **{sym}** dari _{src['name']}_: {e}")
        return f"buy_failed:{e}"

    db.open_position(**pos)
    pid = max(p["id"] for p in db.open_positions() if p["ca"] == pos["ca"])
    agent_line = ""
    if decision:
        db.update_position(pid, tp1_x=decision["tp1"], tp2_x=decision["tp2"], sl_x=decision["sl"])
        agent_line = (f"\n👁 conviction {decision['conviction']} · size {decision['size_mult']:.2f}x · "
                      f"TP {decision['tp1']*100:.0f}/{decision['tp2']*100:.0f} · SL {decision['sl']*100:.0f}\n"
                      f"_{decision['reason']}_"
                      + (f"\n⚠️ risks: {decision['risks']}" if decision.get("risks") else ""))
    if caller_id:
        db.update_position(pid, caller_id=caller_id, caller_name=caller_name)
    cs = db.caller_stats(caller_id)
    caller_line = ""
    if caller_name and cs and cs["calls_bought"] > 1:
        caller_line = (f"\n🎯 caller: {caller_name} — {cs['calls_bought']} call, "
                       f"{cs['hit_tp1'] or 0} TP1, {cs['stopped'] or 0} SL")
    elif caller_name:
        caller_line = f"\n🎯 caller: {caller_name} (baru)"
    hp = "\n⚠️ **SIMULASI SELL GAGAL — kemungkinan HONEYPOT!**" if pos["honeypot"] else ""
    _soc = dx.socials_of(pair)
    soc_line = _soc["label"] if _soc["count"] else "tanpa jejak sosmed"
    chart = f"https://dexscreener.com/{pos['chain_slug']}/{pos['pair_address']}"
    txurl = f"{config.EXPLORER_URL}/tx/{pos['buy_tx']}" if pos.get("buy_tx") else None
    await _notify(
        f"🟢 **BUY {pos['symbol']}**  _via {src['name']}_\n"
        f"`{pos['ca']}`\n"
        f"💰 mcap ${mcap:,.0f} | {_fmt_liq(liq)} | {pos['pool_type']}\n"
        f"🌐 sosmed: {soc_line}\n"
        f"masuk **${pos['usd_spent']:.2f}** ({pos['eth_spent']:.6f} ETH) → {pos['tokens_total']:,.0f} {pos['symbol']}\n"
        f"entry ${pos['entry_price_usd']:.10f}{caller_line}{hp}{agent_line}",
        buttons=[
            [Button.inline("📉 Sell 50%", f"sell:{pid}:50"),
             Button.inline("🚨 Sell ALL", f"sell:{pid}:100")],
            [Button.url("📊 Chart", chart)] + ([Button.url("🔍 Tx", txurl)] if txurl else []),
        ],
    )
    return "bought"
