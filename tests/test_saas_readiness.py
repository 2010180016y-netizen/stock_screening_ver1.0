from __future__ import annotations

import unittest

from vcb_alt.saas_readiness import get_saas_readiness


class SaasReadinessTests(unittest.TestCase):
    def test_saas_readiness_blocks_1000_user_launch(self) -> None:
        report = get_saas_readiness()
        self.assertFalse(report["ready_for_1000_users"])
        self.assertEqual(report["decision"], "NOT_READY_FOR_1000_USER_SAAS")
        self.assertGreaterEqual(report["p0_blocker_count"], 5)

    def test_saas_readiness_includes_security_and_legal_blockers(self) -> None:
        report = get_saas_readiness()
        keys = {item["key"] for item in report["items"]}
        self.assertIn("auth", keys)
        self.assertIn("tenant_isolation", keys)
        self.assertIn("legal", keys)
        self.assertIn("provider_budgeting", keys)


if __name__ == "__main__":
    unittest.main()

