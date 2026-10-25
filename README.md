# Hoodsniper v16.6

Bot sniper on-chain untuk Robinhood Chain (chain id `4663`). Entry dan exit di Uniswap v4 dan v2, plus copy-trade dari wallet insider yang dilacak otomatis.

Bukan bot "AI trading". Logika entry utamanya aritmatika dan pembacaan state pool. LLM cuma dipakai kalau mode MATA dinyalakan, dan itu opsional.

## Yang dipantau

Tiga sumber sinyal, semuanya on-chain:

- event `Initialize` dari factory Uniswap v4 dan v2
- event `TokenLaunched` dari launchpad Pons V2
- pembelian oleh 58 wallet insider, skornya diperbarui tiap posisi ditutup

Wallet insider dirotasi tiap 6 jam. Yang tidak pernah menang dipangkas otomatis.

## Gate entry

Urutannya penting. Yang gagal di awal tidak lanjut ke pemeriksaan yang mahal.

Umur pool 10 sampai 300 detik. Di bawah 10 detik pool masih terlalu dekat dengan deploy, bot tidak ikut masuk. Di atas 5 menit dianggap bukan launch baru.

Likuiditas minimal $4.000. Market cap $5.000 sampai $35.000. Rasio likuiditas terhadap market cap minimal 35%.

Audit bytecode mencari `mint()`, `blacklist()`, dan `setFee()` yang disembunyikan. Dev maksimal pegang 4% supply, top 10 holder di luar pool dan kontrak token maksimal 30%. Kalau Blockscout timeout, token ditolak. Fail-closed, bukan dilewatkan.

Terakhir quoter on-chain dengan `min_out = 0` untuk membaca harga spot asli, bukan harga Dexscreener yang telat 20 sampai 40 detik. Kalau market cap hasil quote di atas $35.000, entry dibatalkan. Token yang dibakar ke `0x...dEaD` dan `0x000...000` dikurangkan dulu dari supply, supaya angka market cap tidak membengkak sekitar 4x.

Ada satu gate lagi khusus jalur insider. Umur pool dicek di tracker, sebelum token masuk pipeline. Token berumur berhari-hari tidak pernah sampai ke tahap audit, tidak lagi menghabiskan kuota RPC dan tidak mengirim notifikasi.

## Dua mode entry

**FAST-PATH** (default). Semua pemeriksaan di atas dihitung dalam milidetik. Nol panggilan LLM.

**MATA**. LLM membaca momentum dan narasi, lalu memberi conviction. Butuh 10 sampai 15 detik. Ada dry-run yang menahan buy kalau LLM tidak menjawab, jadi tidak ada keputusan berarti tidak ada posisi.

## Exit

TP1 di +50%, jual 50%. TP2 di +100%, jual 50% dari sisa. Sisanya jadi moonbag, dijaga trailing stop 20% dari puncak.

Stop loss -30%. Posisi biasa ditutup paksa di menit ke-7 kalau tidak bergerak. Moonbag punya dua batas: tidak aktif selama 7 menit, atau umur total 45 menit.

PnL dihitung dari `quote_sell_eth` on-chain, bukan dari harga layar. Kalau likuiditas pool dicabut, posisi ditutup darurat.

## Pagar tambahan

Clone guard. Keluarga token dikenali dari `sha256(bytecode[:1000])` ditambah symbol dan name. Kalau satu anggota keluarga bikin rug, seluruh keluarga ditandai lewat graf funder deployer. Pengecekan di jalur entry cuma baca DB; enrichment on-chain jalan di background supaya tidak menambah latency.

Rate limit keluarga. Maksimal 3 entry per keluarga operator per 24 jam. Ini yang mencegah bot masuk 9 kali ke pabrik token yang sama.

Launchpad tidak diblokir. Pons tetap jadi sumber sinyal karena di sinilah token baru muncul. Yang dibatasi jumlah entry per keluarga, bukan nama launchpad-nya.

## Mode latihan

Default paper trading. Modal awal $20, tiap entry $5.

Biaya yang dipotong meniru eksekusi nyata: gas 0,0001 ETH, spread entry 2,5%, slippage 2%. Tanpa ini hasil paper akan terlihat lebih bagus daripada kenyataan.

Live butuh wallet burner terpisah dan `WALLET_PRIVATE_KEY` di `.env`.

## Telegram

Panel pakai Bot API resmi. Tidak ada userbot, jadi akun Telegram pribadi tidak ikut berisiko.

Notifikasi buy dan skip membawa angka gate: umur, likuiditas, market cap, rasio, dev, top10, dan market cap on-chain. Alasan skip yang tidak bisa ditindaklanjuti, misalnya umur, tidak dikirim ke Telegram tapi tetap masuk log.

Untuk mengecek satu CA tanpa menunggu bot:

```bash
python3 tools/gate_metrics.py 0x...
```

Perintah itu memakai fungsi gate yang sama dengan bot, jadi angkanya identik. Tambahkan `--fast` kalau mau berhenti di kegagalan pertama.

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
bash tests/run_all.sh        # 23 file tes
pm2 start ecosystem.config.js
pm2 logs hoodsniper-v16
```

## Keamanan

Jangan buka port ke publik. Akses remote lewat Tailscale atau Cloudflare Tunnel.

Pakai wallet burner dengan saldo kecil. Jangan pernah pakai private key dompet utama.

`.env` dan file `.session` harus `chmod 600`.

Kalau audit on-chain gagal karena RPC atau Blockscout bermasalah, token ditolak.
