from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from vcb_alt import config as config_module
from vcb_alt.config import REVOKED_SECRET_HASHES, load_config
from vcb_alt.errors import ValidationError


class RevokedSecretTests(unittest.TestCase):
    """The operator-trial access token leaked through committed documentation.

    Rotating it in the hosting provider is a human step, so the app also refuses to boot
    with a burned credential. Only the digest is stored, never the value.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        saved = {key: os.environ.get(key) for key in ("VCB_ALT_WEB_ACCESS_TOKEN", "VCB_ALT_PUBLIC_WEB_ENABLED")}

        def restore() -> None:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        self.addCleanup(restore)

    def test_revoked_list_is_populated(self) -> None:
        self.assertTrue(REVOKED_SECRET_HASHES)
        for digest in REVOKED_SECRET_HASHES:
            self.assertEqual(len(digest), 64, digest)
            int(digest, 16)  # raises if the entry is not a hex digest

    def test_boot_fails_when_a_revoked_token_is_configured(self) -> None:
        # The burned value is deliberately not written here: repeating it would put the
        # leaked secret back into the repository. Inject a digest instead and check that
        # any listed credential is refused.
        burned = "burned-credential-for-this-test-only"
        digest = hashlib.sha256(burned.encode("utf-8")).hexdigest()

        os.environ["VCB_ALT_PUBLIC_WEB_ENABLED"] = "true"
        os.environ["VCB_ALT_WEB_ACCESS_TOKEN"] = burned
        with mock.patch.object(config_module, "REVOKED_SECRET_HASHES", frozenset({digest})):
            with self.assertRaises(ValidationError) as caught:
                load_config(self.root)
        self.assertIn("publicly exposed", str(caught.exception))

    def test_a_fresh_token_is_accepted(self) -> None:
        os.environ["VCB_ALT_PUBLIC_WEB_ENABLED"] = "true"
        os.environ["VCB_ALT_WEB_ACCESS_TOKEN"] = "kQ7wm2ZpLd4TnX9bVs6RhY1cJe8FgA3u"
        config = load_config(self.root)
        self.assertTrue(config.public_web_enabled)


if __name__ == "__main__":
    unittest.main()
