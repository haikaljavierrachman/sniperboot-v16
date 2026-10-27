# Hoodsniper v16.8

Bot sniper on-chain murni **Uniswap v4** untuk **Robinhood Chain** (`chainId 4663`), dilengkapi radar intel **Insider Tracker** yang terpisah dari pipa eksekusi.

Bukan bot "AI trading". Logika entry dan exit utamanya berbasis pembacaan state pool Uniswap v4 (`PoolManager`, `StateView`, dan `V4Quoter`) secara langsung di atas rantai. LLM hanya dipakai bila mode MATA diaktifkan secara eksplisit.

## Arsitektur Sumber Sinyal (v16.8)

1. **On-Chain Scanner (Murni Uniswap v4):**
   - Memantau event `Initialize` langsung dari kontrak `PoolManager` Uniswap v4 (`0x05b5...`). Seluruh jalur warisan Uniswap v2/v3 dan Pons telah dihapus dari hulu ke hilir.
   - **Antrean Retry Cerdas (`pending_pools`):** Koin v4 baru yang belum ter-index atau masih menunggu likuiditas ditahan di antrean dan dicoba ulang tiap `20 detik` sampai lolos atau melewati batas umur maksimal.

2. **Insider Tracker (Alert-Only Radar + Log Beli Insider):**
   - Berjalan **terpisah penuh dari pipa eksekusi buy** (`insider_alert_only=1` default): tidak membuka posisi otomatis, tanpa batas umur pool (*age gate*), dan nol panggilan RPC tambahan.
   - **Dedup Per-CA (10 Menit):** Satu koin maksimal mengirim 1 notifikasi ke ruang chat tiap 10 menit meskipun dibeli oleh banyak dompet insider sekaligus.
   - **Panel `🔥 Log Beli Insider`:** Seluruh transaksi beli dari dompet insider direkam ke tabel `insider_buys` dan dapat dipantau kapan saja lewat menu **`📡 Sources` → `🔥 Log Beli Insider`** (filter `10m`, `1 Jam`, `24 Jam`, diurutkan berdasarkan jumlah transaksi & dompet unik).

## Gate Entry

Urutan saringan dirancang dari yang paling murah ke pemeriksaan on-chain:

- **Umur Pool:** `10` sampai `300 detik` (5 menit).
- **Likuiditas & Market Cap:** Likuiditas minimal **$4.000**, Market Cap **$5.000 – $35.000**, dan rasio Likuiditas/Market Cap minimal **35%**.
- **Audit Keamanan (Fail-Closed):** Pemeriksaan bytecode (`mint`, `blacklist`, `setFee`), kepemilikan Dev maksimal **4%**, dan Top 10 Holder (di luar pool/kontrak) maksimal **30%**. Bila Blockscout atau RPC gagal merespons, token otomatis ditolak.
- **Kuoter Spot On-Chain (`V4Quoter`):** Menghitung harga beli riil dan *effective market cap* setelah dikurangi token yang sudah dibakar (`0x...dEaD` & `0x000...000`). Seluruh notifikasi BUY menampilkan **100% Market Cap On-Chain aktual**, bukan angka cache layar Dexscreener.

## Pagar Anti-Scam & Clone Guard

- **Clone / Operator-Family Guard:** Mengenali keluarga koin dari sidik jari bytecode ditambah simbol, nama, serta jaringan pendana (*funder*) deployer. Jika satu koin dalam keluarga terdeteksi rug, kloningan berikutnya langsung ditolak di jalur cepat.
- **Rate Limit Keluarga:** Maksimal **3 entry per keluarga operator per 24 jam**.

## Strategi Exit Anti-Cabut LP (v16.8)

Berdasarkan audit riwayat pool Uniswap v4 di Robinhood Chain, mayoritas pencabutan likuiditas (*LP pull*) oleh deployer terjadi pada rentang menit ke-5 hingga ke-7 (`300s–425s`). Parameter exit v16.8 dikalibrasi untuk keluar sebelum jendela tersebut:

- **TP1 di `+20%`:** Jual **60%** posisi untuk mengamankan modal pokok lebih dini.
- **TP2 di `+45%`:** Jual **100% sisa posisi** (tanpa menyisakan *moonbag* yang rawan hangus saat pool dicabut).
- **Time-Stop `240 Detik` (4 Menit):** Posisi yang belum menyentuh target ditutup bersih pada menit ke-4, sebelum jendela rata-rata dev mencabut LP.
- **Stop Loss `-30%` & Deteksi Darurat LP Kosong:** Bila `v4.get_pool_liquidity` mendeteksi likuiditas on-chain jatuh ke `0`, bot langsung memicu *emergency exit*.
- **Basis Harga On-Chain Seragam:** Perhitungan `pnl`, `peak_price`, dan *trailing stop* di `engine.py` seluruhnya diturunkan dari hasil kuoter jual `V4Quoter` on-chain (`quote_sell_eth`), sehingga bebas dari pemicu palsu akibat jeda cache harga layar.

## Mode Latihan (Paper Trading)

- Menggunakan kuoter beli (`quote_buy_tokens`) dan kuoter jual (`quote_sell_eth`) Uniswap v4 secara langsung di atas blockchain, lengkap dengan potongan spread entry (`2,5%`), slippage, dan beban gas.
- Dilengkapi tombol **`🔄 Reset Saldo`** di panel **`💼 Wallet`** Telegram yang memungkinkan pengisian ulang saldo virtual dengan nominal USD bebas kapan saja.

## Diagnostik Cepat

Untuk menguji kelayakan satu alamat kontrak (CA) terhadap seluruh gerbang saringan tanpa menunggu siklus bot:

```bash
python3 tools/gate_metrics.py 0x...
```

## Menjalankan

Prasyarat: Linux, Python 3.11+, RPC Robinhood Chain, token bot dari BotFather, dan satu wallet burner.

```bash
git clone git@github.com:irf4an/sniperboot-v16.git
cd sniperboot-v16
pip install -r requirements.txt
cp .env.example .env
chmod 600 .env
```

Isi `.env`: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ADMIN_ID`, `RPC_URL`, `WALLET_PRIVATE_KEY`.

```bash
bash tests/run_all.sh
pm2 start ecosystem.config.js
pm2 logs hoodsniper-v16
```

## Keamanan

- Jangan pernah membuka port ke publik; gunakan Tailscale atau Cloudflare Tunnel.
- Gunakan dompet *burner* khusus dengan modal terukur, jangan gunakan *private key* dompet utama.
- Pastikan `.env` dan seluruh file database/backup memiliki izin akses `chmod 600`.
