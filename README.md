# Hoodsniper v16.4 🤖⚡

Autonomous On-Chain Sniper & Multi-DEX Trading Bot untuk **Robinhood Chain (Chain ID `4663`)**. Dilengkapi arsitektur hybrid: **Audit Bytecode Deterministik + Zero-Gas On-Chain Quoter + AI Reasoning (MATA & TANGAN) + Mobile Telegram Control Panel**.

---

## ⚡ Cara Kerja Bot (Alur Pipeline Eksekusi)

```
[Sumber Sinyal]
  ├── Factory Events (v2, v3, v4 via eth_getLogs)
  ├── Smart Money Tracker (55 Insider Wallets Copy-Trade)
  ├── Pending Pool Retry Queue (Anti-Stale Index Dexscreener)
  └── Telegram Listener (Telethon Userbot Alpha Groups)
          │
          ▼
[Lapisan 1: Pagar Keras Pre-Buy (0.05s)]
  ├── Filter Market Cap: $7.000 – $45.000 (Anti-Pucuk)
  ├── Filter Likuiditas: Min $2.000 (Rasio Liq/Mcap Sehat)
  ├── Audit Bytecode EVM: Deteksi fungsi mint(), blacklist(), setFee() tersembunyi
  └── Audit Holder: Dev max 5%, Top 10 non-pool max 40% (via Blockscout)
          │
          ▼
[Lapisan 2: Kecerdasan Buatan — MATA (LLM)]
  ├── Evaluasi Momentum: Volume flow (buys vs sells), pool age, pump vertikal
  └── Dynamic Sizing: Tentukan size modal (0.5x – 1.0x) & target TP/SL kustom
          │
          ▼
[Lapisan 3: Zero-Gas On-Chain Quoter (Detik Eksekusi)]
  ├── Simulasi eth_call langsung ke Sequencer (Tanpa Gas)
  │     ├── Uniswap v4 : V4Quoter.quoteExactInputSingle + StateView
  │     ├── Uniswap v3 : SwapRouter02
  │     └── Uniswap v2 : Router2.getAmountsOut
  ├── Pagar Slippage: Tolak jika harga sudah lari > 60%
  └── Pagar Mcap Riil: Tolak jika Mcap On-Chain > $45.000 (Terkunci oleh sniper lain)
          │
          ▼
[Lapisan 4: Eksekusi Swap & Posisi]
  ├── Live Mode     : Kirim Raw Transaction (UniversalRouter / SwapRouter)
  └── Latihan Mode  : Virtual Paper Trading presisi tinggi (Potong gas $0.12 + slip 1%)
          │
          ▼
[Lapisan 5: Mesin Penjaga Posisi (Loop Matematika Tiap 20s)]
  ├── TP1 Scale-Out : Jual 50% di +35% / +50% (Modal aman di kantong)
  ├── Breakeven SL  : Sisa moonbag terkunci minimal di harga modal (0% risk)
  ├── TP2 Target    : Kunci profit bersih di +80% / +100%
  ├── Trailing ATH  : Kunci cuan jika grafik turun -15% dari titik puncak (ATH)
  ├── Hard Rug Exit : Auto-sell seketika jika likuiditas pool dicabut dev
  └── TANGAN (AI)   : Review berkala tiap 10 menit untuk cut-loss posisi basi
```

---

## 🛠 Fitur Utama

- **Dukungan Multi-DEX Penuh**:
  - **Uniswap v4**: UniversalRouter (`0x8876...0904`), StateView (`0x0284...55F2`), V4Quoter (`0xdF8B...1867`).
  - **Uniswap v3**: SwapRouter02 & Tick Fee decoding.
  - **Uniswap v2**: Router2 getAmountsOut & Fee-on-transfer support.
- **Konkurensi Cepat & Ringan**:
  - `Batch 2` + `asyncio.Semaphore(2)` memangkas jeda antrean dari 30s menjadi 6s tanpa membebani rate limit RPC.
  - RAM VPS super hemat: konsisten $\le$ 120 MB.
- **Realistic Virtual Paper Trading**:
  - Mensimulasikan kondisi riil blockchain: gas sequencer L2 ($0.12 per swap), spread eksekusi DEX 1%, dan harga live On-Chain Quoter (bukan ilusi harga layar Dexscreener).
- **Mobile Telegram Control Panel**:
  - Atur modal, TP/SL, slippage, refresh data, switch latihan/live, pantau grafik posisi, dan intervensi manual (Sell 50% / Sell ALL) langsung dari Telegram.

---

## 🚀 Setup Cepat

### 1. Prasyarat
- Python 3.11+
- Node.js (opsional untuk helper)
- Akun Telegram (API ID & Hash dari `my.telegram.org`)
- Bot Telegram (Token dari `@BotFather`)

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
# Jalankan langsung
python3 bot.py

# Atau via PM2 (rekomendasi VPS)
pm2 start ecosystem.config.js
```

---

## ⚖️ Lisensi & Keamanan
Khusus untuk riset dan otomatisasi pada aset terotorisasi. Selalu gunakan **burner wallet terpisah** dengan saldo terbatas.
