"""Unit test untuk Sybil Cluster Guard (anti wash-trading dev bot di insider tracker)."""
import os
import sys
import unittest
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sniper import config, db


class TestSybilGuard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()
        self.old_db_path = config.DB_PATH
        config.DB_PATH = self.db_path
        db.init()

    def tearDown(self):
        config.DB_PATH = self.old_db_path
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_detect_and_purge_sybil_cluster(self):
        ca = "0x66bc1590b1039faf965821f8fbfe08a05c43f081"
        now = int(time.time())
        wallets = [f"0x{'%02x' % i * 20}" for i in range(1, 8)]

        # Daftarkan 7 wallet sebagai insider
        for w in wallets:
            db.add_insider_wallet(w, label="test", win_count=5, enabled=1)

        # 7 wallet serempak beli CA yang sama dalam 20 detik
        for idx, w in enumerate(wallets):
            db.record_insider_buy(ca, wallet=w, symbol="FAKE", ts=now + idx * 3)

        # Jalankan deteksi
        clusters = db.detect_and_purge_sybil_clusters(min_wallets=7, window_sec=60, ca=ca)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0]["ca"], ca)
        self.assertEqual(len(clusters[0]["wallets"]), 7)

        # Pastikan seluruh 7 wallet masuk blacklist
        for w in wallets:
            self.assertTrue(db.is_sybil_blacklisted(w))
            # Pastikan di insider_wallets status enabled=0 & label='sybil_cluster'
            r = [x for x in db.list_insiders() if x["address"] == w][0]
            self.assertEqual(r["enabled"], 0)
            self.assertEqual(r["label"], "sybil_cluster")

        # Pastikan pembelian sybil bersih dari insider_buys
        with db._conn() as c:
            count = c.execute("SELECT COUNT(*) FROM insider_buys WHERE ca=?", (ca,)).fetchone()[0]
            self.assertEqual(count, 0)

    def test_legitimate_staggered_buys_not_purged(self):
        ca = "0xe4119a9bfcc86915368502b598bbed4745f7051d"
        now = int(time.time())
        wallets = [f"0x{'%02x' % (i + 10) * 20}" for i in range(7)]

        for w in wallets:
            db.add_insider_wallet(w, label="organic", win_count=3, enabled=1)

        # 7 wallet beli bertahap (jeda 100 detik tiap wallet -> span 600 detik)
        for idx, w in enumerate(wallets):
            db.record_insider_buy(ca, wallet=w, symbol="LEGIT", ts=now + idx * 100)

        clusters = db.detect_and_purge_sybil_clusters(min_wallets=7, window_sec=60, ca=ca)
        self.assertEqual(len(clusters), 0)

        # Pastikan tidak ada yang di-blacklist
        for w in wallets:
            self.assertFalse(db.is_sybil_blacklisted(w))
            r = [x for x in db.list_insiders(only_enabled=True) if x["address"] == w][0]
            self.assertEqual(r["enabled"], 1)

    def test_sybil_blacklisted_wallet_cannot_be_readded(self):
        w = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        # Blacklist manual
        with db._conn() as c:
            c.execute("INSERT INTO sybil_blacklist (address, reason, detected_at) VALUES (?, ?, ?)",
                      (w, "sybil test", int(time.time())))

        # Coba rekrut ulang lewat add_insider_wallet
        res = db.add_insider_wallet(w, label="auto_rotate", win_count=10)
        self.assertFalse(res)


if __name__ == "__main__":
    unittest.main()
