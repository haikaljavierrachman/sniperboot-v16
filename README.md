# Hoodsniper v16.6 🤖⚡

Autonomous On-Chain Sniper & Multi-DEX Trading Bot untuk **Robinhood Chain (Chain ID `4663`)**. Dilengkapi arsitektur **Dual-Engine Entry (MATA AI $\leftrightarrow$ FAST-PATH 0s Math)**, **Zero-Gas On-Chain Quoter**, **55 Insider Smart Money Copy-Tracker**, serta **Panel Kontrol Telegram Resmi (BotFather)** tanpa memerlukan userbot akun personal.

---

## ⚡ Cara Kerja Bot (Alur Pipeline Eksekusi)

```
[Sumber Sinyal Murni On-Chain]
  ├── Factory Events (Uniswap v2, v3, v4 via eth_getLogs)
  ├── Smart Money Tracker (55 Insider Wallets Copy-Trade)
  └── Pending Pool Retry Queue (Anti-Stale Index Dexscreener)
          │
          ▼
[Lapisan 1: Pagar Keras Pre-Buy (0.05s)]
  ├── Filter Market Cap: $7.000 – $45.000 (Anti-Pucuk)
  ├── Filter Likuiditas: Min $2.000 – $4.000 (Rasio Liq/Mcap Sehat)
  ├── Audit Bytecode EVM: Deteksi fungsi mint(), blacklist(), setFee() tersembunyi
  └── Audit Holder: Dev max 3% – 5%, Top 10 non-pool max 25% – 40% (via Blockscout)
          │
          ▼
[Lapisan 2: Dual-Engine Entry Gate (Pilih via Saklar Telegram)]
  ├── 👁 MODE MATA (LLM) :
  │     Evaluasi momentum pasar, volume flow, chart curve, & dynamic sizing (5–7s).
  └── ⚡ MODE FAST-PATH (Goldilocks Defensive) :
        Evaluasi murni matematika & umur pool (30s–180s), rasio liq/mcap ≥ 35% (0.2s, 0 detik LLM).
          │
          ▼
[Lapisan 3: Zero-Gas On-Chain Quoter (Detik Eksekusi)]
  ├── Simulasi eth_call langsung ke Sequencer (Tanpa Gas)
  │     ├── Uniswap v4 : UniversalRouter + V4Quoter.quoteExactInputSingle + StateView
  │     ├── Uniswap v3 : SwapRouter02
  │     └── Uniswap v2 : Router2.getAmountsOut
  ├── Pagar Slippage: Tolak jika harga lari melebihi batas toleransi
  └── Pagar Mcap Riil: Tolak jika Mcap On-Chain > $45.000 (Terkunci oleh sniper lain)
          │
          ▼
[Lapisan 4: Eksekusi Swap & Posisi]
  ├── Live Mode     : Kirim Raw Transaction (UniversalRouter / SwapRouter)
  └── Latihan Mode  : Virtual Paper Trading presisi tinggi (Potong gas $0.12 + slip 1%)
          │
          ▼
[Lapisan 5: Mesin Penjaga Posisi (Loop Matematika Tiap 20s)]
  ├── TP1 Scale-Out : Jual 50% di +35% / +50% (Modal pokok kembali aman ke kas)
  ├── Breakeven SL  : Sisa moonbag terkunci minimal di harga modal (0% risk)
  ├── TP2 Target    : Kunci profit bersih di +80% / +100%
  ├── Trailing ATH  : Kunci cuan jika grafik turun -15% dari titik puncak (ATH)
  ├── Hard Rug Exit : Auto-sell seketika jika likuiditas pool dicabut dev
  └── TANGAN (AI)   : Review berkala tiap 10 menit untuk cut-loss posisi basi
```

---

## 🛠 Fitur Utama

- **Dual-Engine Entry Switch**:
  - Pindah mode instan lewat 1 tombol di Telegram: `👁 MATA (LLM)` untuk analisis mendalam vs `⚡ FAST-PATH (Math)` untuk sambaran kilat (0.2 detik).
- **100% On-Chain & Aman dari Risiko Banned Telegram**:
  - Telethon userbot akun pribadi didekopel penuh (`userbot_enabled: 0`).
  - Bot berjalan murni menggunakan bot resmi Telegram (`@BotFather`). Akun personal Anda bebas risiko ban atau spam-block.
- **Dukungan Multi-DEX Penuh**:
  - **Uniswap v4**: UniversalRouter (`0x8876...0904`), StateView (`0x0284...55F2`), V4Quoter (`0xdF8B...1867`).
  - **Uniswap v3**: SwapRouter02 & Tick Fee decoding.
  - **Uniswap v2**: Router2 getAmountsOut & Fee-on-transfer support.
- **Konkurensi Ringan & Hemat Sumber Daya**:
  - `Batch 2` + `asyncio.Semaphore(2)` memangkas antrean screening.
  - Pemakaian RAM VPS stabil di $\le$ 110 MB (cocok untuk VPS RAM 3.5 GB tanpa GPU).
- **Realistic Virtual Paper Trading Simulator**:
  - Mensimulasikan kondisi riil blockchain: gas sequencer L2 ($0.12 per swap), spread eksekusi DEX 1%, dan harga live On-Chain Quoter.
- **Mobile Telegram Control UI**:
  - Atur modal, TP/SL, slippage, refresh data, switch latihan/live, pantau grafik posisi, dan intervensi manual (Sell 50% / Sell ALL) langsung dari Telegram.

---

## 🚀 Setup Cepat

### 1. Prasyarat
- Python 3.11+
- Bot Telegram (Token dari `@BotFather` & Admin ID dari `@userinfobot`)
- RPC Robinhood Chain (atau EVM L2 target)

### 2. Instalasi
```bash
git clone git@github.com:irf4an/sniperboot-v16.git
cd sniperboot-v16
pip install -r requirements.txt
cp .env.example .env
```

### 3. Konfigurasi (.env)
Isi variabel pada `.env` (private key burner, token Telegram, admin ID, dan URL LLM jika mode AI aktif).

### 4. Menjalankan
```bash
# Jalankan langsung (Plug & Play, tanpa perlu scan QR akun Telegram)
python3 bot.py

# Atau via PM2 (rekomendasi VPS)
pm2 start ecosystem.config.js
```

---

## ⚖️ Lisensi & Keamanan
Khusus untuk riset dan otomatisasi pada aset terotorisasi. Selalu gunakan **burner wallet terpisah** dengan saldo terbatas.
