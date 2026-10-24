# Hoodsniper v16.6 🤖⚡

Autonomous On-Chain Sniper & Multi-DEX Trading Bot untuk **Robinhood Chain (Chain ID `4663`)**. Dirancang khusus untuk pertarungan blok sequencer berkecepatan tinggi ($\sim 0.15 - 0.20$ detik/blok), bot ini mengusung **Duopoli DEX (Uniswap v4 + v2)**, **Arsitektur Dual-Engine Entry (FAST-PATH 0s Math $\leftrightarrow$ MATA LLM)**, **On-Chain Spot Price Anchor**, **Sinkronisasi PnL On-Chain Sell Quoter**, serta **55 Insider Smart Money Copy-Tracker** dengan **Panel Kontrol Telegram Resmi (BotFather)** murni 100% on-chain.

---

## ⚡ Arsitektur Pipeline Eksekusi (High-Speed Engine)

```
[Sumber Sinyal Murni On-Chain]
  ├── Factory Events Duopoli (Uniswap v4 & Uniswap v2 via eth_getLogs)
  ├── Smart Money Copy-Tracker (55 Insider Wallets, Rotasi 6 Jam, Pruning 3 Hari)
  └── Pending Pool Retry Queue (Penjaga Gap Indeks Dexscreener)
          │
          ▼
[Lapisan 1: Pagar Keras Pre-Screening (0.02s)]
  ├── Duopoli Guard: Pemblokiran total Uniswap v3 (Tick-Trap 100% Rug) & Pons Launchpad
  ├── Filter Umur Pool: 10 detik s/d 300 detik (5 menit, melompati MEV dev blok 1–5)
  ├── Filter Likuiditas: Min $4.000 (Rasio Liq/Mcap Sehat ≥ 35%)
  ├── Audit Bytecode EVM: Deteksi fungsi mint(), blacklist(), setFee() tersembunyi
  └── Audit Holder: Dev max 4%, Top 10 non-pool max 30% (Fail-closed via Blockscout)
          │
          ▼
[Lapisan 2: Dual-Engine Entry Gate (Pilih via Saklar Telegram)]
  ├── ⚡ MODE FAST-PATH (Goldilocks Defensive - Default & Rekomendasi):
  │     Evaluasi murni matematika/bytecode dalam 0.01 detik (0 detik LLM).
  │     Langsung menyambar blok sequencer bersama sniper profesional tanpa buang 100 blok.
  └── 👁 MODE MATA (LLM Opsional):
        Evaluasi momentum narasi & konfirmasi conviction via AI (10–15s).
          │
          ▼
[Lapisan 3: On-Chain Spot Price Anchor & Zero-Gas Quoter (Detik Eksekusi)]
  ├── Spot Price Anchor: Probe harga spot riil dari pool (min_out = 0), bebas lag Dexscreener
  ├── Circulating Supply Guard: Pengurangan token burned (0x...dEaD & 0x...000) untuk hitungan Mcap presisi
  ├── Pagar Market Cap On-Chain: Tolak masuk jika Mcap On-Chain > $35.000 (Anti-Pucuk)
  └── Toleransi Slippage 2 Lapis:
        ├── Lapis 1 Screener: Max 25% (mencegah false reject koin yang berfluktuasi wajar)
        └── Lapis 2 Swap On-Chain: Toleransi AMM 40% (tembus blok sequencer tanpa revert)
          │
          ▼
[Lapisan 4: Eksekusi Swap & Posisi]
  ├── Live Mode     : Kirim Raw Transaction ke Uniswap v4 UniversalRouter / v2 Router
  └── Latihan Mode  : Virtual Paper Trading presisi tinggi (Modal awal $20, Gas $0.12, Spread 1%)
          │
          ▼
[Lapisan 5: Mesin Penjaga Posisi & Sinkronisasi PnL On-Chain (Engine Loop 5s)]
  ├── On-Chain PnL Sync : Evaluasi PnL mengacu langsung pada output quote_sell_eth (Bebas lag layar)
  ├── TP1 Scale-Out     : Jual 50% di +35% / +50% (Modal pokok langsung kembali aman ke dompet/kas)
  ├── TP2 Target        : Kunci profit puncak di +80% / +100% (TETAP AKTIF)
  ├── Breakeven & Trail : Kunci profit jika grafik anjlok -15% dari titik puncak (ATH)
  ├── Hard Rug Exit     : Emergency exit seketika jika StateView mendeteksi likuiditas pool dicabut
  └── Time-Stop Lifespan: Auto-close posisi setelah 20 menit (1200s) jika pergerakan stagnan
```

---

## 🛠 Perombakan Besar & Keunggulan Rekayasa Sistem (v16.6)

### 1. Duopoli DEX (Uniswap v4 + Uniswap v2)
* **Penghapusan Uniswap v3 & Pons Launchpad**: Data historis menunjukkan Uniswap v3 menjadi sarang *tick-trap* sempit yang memicu 100% transaksi rug, sementara Pons memiliki volume pasar insignifikan (<2%).
* **Efisiensi RPC**: Scanner hanya mendengarkan `factory-v4` (UniversalRouter) dan `factory-v2`, memangkas beban kuota RPC `eth_getLogs` hingga 50%.

### 2. On-Chain Spot Price Anchor (Bebas Lag Dexscreener)
* Dexscreener memiliki *cache delay* 20–40 detik. Koin runner yang melonjak dari Mcap $8k ke $15k sebelumnya ditolak dengan alasan `slippage_besar` palsu karena membandingkan harga on-chain dengan harga layar lama.
* Bot kini meng-anchor harga menggunakan **kuotasi spot on-chain langsung dari pool**.
* Selama $\text{Mcap On-Chain} \le \$35.000$, bot langsung hajar masuk tanpa terhadang slippage palsu.

### 3. Deteksi Burned Supply (Circulating Market Cap Presisi)
* Meme coin di L2 Robinhood mayoritas membakar $\sim 77.2\%$ dari 1 Miliar token awal ke alamat `0x000000000000000000000000000000000000dEaD`.
* Bot membaca saldo alamat bakar secara on-chain dan mengurangkannya dari total supply:
  $$\text{Circulating Supply} = \text{Total Supply} - \text{Burned Tokens}$$
* Menghilangkan kesalahan tuduhan `mcap_onchain_pucuk` dan menyelaraskan perhitungan market cap bot 100% presisi dengan Dexscreener.

### 4. Sinkronisasi PnL On-Chain Sell Quoter (`engine.py`)
* Pemantauan posisi (TP1, TP2, Stop Loss, Trailing Stop) dan realisasi exit simulasi kini menggunakan **`quote_sell_eth`** langsung dari blockchain.
* Mengeliminasi bug desinkronisasi di mana posisi yang baru dibeli di on-chain langsung terkena Stop Loss palsu di detik pertama akibat grafik layar Dexscreener yang belum naik.

### 5. Aturan Siklus Hidup Meme Coin & Smart Money Tracker
* **Time-Stop 20 Menit (`closed_timeout`)**: Membebaskan modal trading jika token tidak mencapai target dalam 20 menit.
* **Auto-Blacklist Insider**: Wallet yang memicu 2x Stop Loss berturut-turut langsung dinonaktifkan (`enabled = 0`).
* **Pruning Pasif 3 Hari**: Wallet inaktif > 72 jam dengan kemenangan $< 2$ koin dipangkas otomatis setiap rotasi 6 jam.

### 6. Proteksi Akumulasi Saldo Paper Trading
* Default modal uji coba dirasionalisasi menjadi **$20.00** (sesuai standar bankroll disiplin).
* Skrip `tools/reset_paper_wallet.py` dirombak total dengan **dialog konfirmasi interaktif `[y/N]`** dan opsi argumen nominal fleksibel, mencegah reset tidak disengaja terhadap akumulasi profit riil.

---

## 📱 Kontrol Telegram BotFather (100% Murni On-Chain)

Bot berjalan sepenuhnya menggunakan API BotFather resmi tanpa ketergantungan Telethon userbot akun personal (`userbot_enabled: 0`), menjamin akun Telegram personal Anda bebas dari risiko banned:

* **Panel Utama**: Status kas virtual, saldo ETH wallet burner, posisi terbuka, dan ringkasan PnL.
* **Saklar 1-Klik**:
  * Mode Entry: `⚡ FAST-PATH` (Math 0s) $\leftrightarrow$ `👁 MATA` (LLM).
  * Mode Lingkungan: `🧪 Latihan (Paper Trading)` $\leftrightarrow$ `🔴 Live On-Chain`.
* **Intervensi Posisi**: Tombol aksi darurat langsung di notifikasi (`Jual 50%` / `Jual 100%`).

---

## 🚀 Setup & Menjalankan

### 1. Prasyarat Sistem
* Linux / macOS (Diuji pada Ubuntu 22.04 LTS, RAM $\ge$ 3.5 GB, Zero-Inbound Ports)
* Python 3.11+
* Kredensial Bot Telegram dari `@BotFather` & Chat ID Admin dari `@userinfobot`
* RPC Node Robinhood Chain (EVM Chain ID `4663`)

### 2. Instalasi
```bash
git clone git@github.com:irf4an/sniperboot-v16.git
cd sniperboot-v16
pip install -r requirements.txt
cp .env.example .env
chmod 600 .env
```

### 3. Konfigurasi (`.env`)
Isi variabel lingkungan yang diperlukan:
* `TELEGRAM_BOT_TOKEN`: Token bot dari BotFather
* `TELEGRAM_ADMIN_ID`: ID akun Telegram Anda
* `RPC_URL`: Endpoint RPC Robinhood Chain
* `WALLET_PRIVATE_KEY`: Private key wallet burner terdedikasi

### 4. Eksekusi & Manajemen Proses
```bash
# Uji seluruh test suite regresi (18 file tes wajib lulus 100%)
bash tests/run_all.sh

# Menjalankan via PM2 (rekomendasi VPS)
pm2 start ecosystem.config.js

# Memantau log real-time
pm2 logs hoodsniper-v16
```

---

## 🛡 Kebijakan Keamanan & Manajemen Resiko
1. **Zero Inbound Port**: Jangan membuka port server ke publik; akses dashboard/panel remote hanya melalui VPN/Tailscale atau Cloudflare Tunnel.
2. **Burner Wallet Only**: Dilarang keras menggunakan private key dompet utama. Selalu gunakan dompet burner dengan saldo operasional minimal (\$20 – \$30).
3. **Fail-Closed Safety**: Jika audit holder Blockscout atau StateView RPC mengalami gangguan/timeout, sistem secara otomatis menolak token (`fail-closed`).
