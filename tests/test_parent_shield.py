"""Unit test untuk Parent Shield & Auto-Discovery Koin Induk (sniper/clone_guard.py)."""
import os
import sys
import unittest
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sniper import config, clone_guard, db


class TestParentShield(unittest.TestCase):
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

    def test_upsert_and_get_parent(self):
        clone_guard.upsert_parent_token(
            symbol="WOFL",
            ca="0xe4119a9bfcc86915368502b598bbed4745f7051d",
            name="WOFL / USDG",
            mcap=500000.0,
            liq=60000.0,
            source="test"
        )
        p = clone_guard.get_parent_token("wofl")
        self.assertIsNotNone(p)
        self.assertEqual(p["symbol"], "WOFL")
        self.assertEqual(p["ca"], "0xe4119a9bfcc86915368502b598bbed4745f7051d")
        self.assertEqual(p["mcap"], 500000.0)

    def test_clone_parasite_rejected(self):
        parent_ca = "0xe4119a9bfcc86915368502b598bbed4745f7051d"
        clone_ca = "0x62ee9da7bffac42459c00e9048fb489373b26798"
        clone_guard.upsert_parent_token(
            symbol="WOFL",
            ca=parent_ca,
            name="WOFL Parent",
            mcap=450000.0,
            liq=50000.0
        )

        risk, reason = clone_guard.is_clone_risk(clone_ca, symbol="WOFL", name="WOFL")
        self.assertTrue(risk)
        self.assertIn("klon parasit dari induk WOFL", reason)
        self.assertIn(parent_ca[:10], reason)

    def test_genuine_parent_allowed(self):
        parent_ca = "0xe4119a9bfcc86915368502b598bbed4745f7051d"
        clone_guard.upsert_parent_token(
            symbol="WOFL",
            ca=parent_ca,
            name="WOFL Parent",
            mcap=450000.0,
            liq=50000.0
        )

        risk, reason = clone_guard.is_clone_risk(parent_ca, symbol="WOFL", name="WOFL")
        self.assertFalse(risk)
        self.assertEqual(reason, "clone_guard: bersih")

    def test_novel_token_allowed(self):
        novel_ca = "0x1111111111111111111111111111111111111111"
        risk, reason = clone_guard.is_clone_risk(novel_ca, symbol="BRANDNEW", name="Brand New")
        self.assertFalse(risk)
        self.assertEqual(reason, "clone_guard: bersih")


if __name__ == "__main__":
    unittest.main()
