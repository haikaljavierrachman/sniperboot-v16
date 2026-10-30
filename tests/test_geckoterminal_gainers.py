"""Unit test untuk integrasi GeckoTerminal pada fetch_gainers (tools/screen_insiders.py)."""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import screen_insiders as si
from sniper import geckoterminal as gt


class TestGeckoTerminalGainers(unittest.TestCase):
    def test_geckoterminal_rh_cas_parser(self):
        sample_pools = [
            {
                "attributes": {
                    "name": "GIGATENEV / WETH",
                    "volume_usd": {"h24": "1250000.5"},
                    "price_change_percentage": {"h24": "-15.2"},
                },
                "relationships": {
                    "base_token": {"data": {"id": "robinhood_0xc9675fe679c7d4e1b94416f66d61c96127eb964a"}},
                    "quote_token": {"data": {"id": "robinhood_0x0bd7d308f8e1639fab988df18a8011f41eacad73"}},
                },
            },
            {
                "attributes": {
                    "name": "WOFL / USDG",
                    "volume_usd": {"h24": "500000.0"},
                    "price_change_percentage": {"h24": "300.0"},
                },
                "relationships": {
                    "base_token": {"data": {"id": "robinhood_0xe4119a9bfcc86915368502b598bbed4745f7051d"}},
                    "quote_token": {"data": {"id": "robinhood_0x5fc5360d0400a0fd4f2af552add042d716f1d168"}},
                },
            },
        ]
        with patch.object(gt, "trending_pools", return_value=sample_pools), \
             patch.object(gt, "pools", return_value=[]):
            cas = si._geckoterminal_rh_cas()
            self.assertEqual(len(cas), 2)
            c_dict = {c: (v, chg) for v, chg, c in cas}
            giga = "0xc9675fe679c7d4e1b94416f66d61c96127eb964a"
            wofl = "0xe4119a9bfcc86915368502b598bbed4745f7051d"
            self.assertIn(giga, c_dict)
            self.assertIn(wofl, c_dict)
            self.assertAlmostEqual(c_dict[giga][0], 1250000.5)
            self.assertAlmostEqual(c_dict[wofl][1], 300.0)

    def test_fetch_gainers_includes_geckoterminal(self):
        sample_gt = [
            (100000.0, 50.0, "0x1111111111111111111111111111111111111111"),
            (500000.0, 20.0, "0x2222222222222222222222222222222222222222"),
        ]
        with patch.object(si, "_geckoterminal_rh_cas", return_value=sample_gt), \
             patch.object(si, "_dexscreener_profiles_cas", return_value=[]), \
             patch.object(si, "_get", side_effect=Exception("skip dexscreener")):
            res = si.fetch_gainers(limit=2)
            self.assertEqual(res, [
                "0x2222222222222222222222222222222222222222",
                "0x1111111111111111111111111111111111111111",
            ])


if __name__ == "__main__":
    unittest.main()
