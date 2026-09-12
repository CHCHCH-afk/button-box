import os
from pathlib import Path
import subprocess
import unittest


class UpgradeInstructionsTests(unittest.TestCase):
    def completion(self, *, existing=True, target=""):
        setup = (Path(__file__).resolve().parents[1] / "scripts/setup.sh").read_text()
        start = setup.index("# Existing installations keep")
        end = setup.index('if [ -n "$SSH_TARGET" ]; then\n  dev_command=', start)
        script = 'hostname() { printf "%s\\n" "message-box-042"; }\n' + setup[start:end]
        script += 'printf "%s\\n" "FRESH_INSTALL_FLOW"\n'
        return subprocess.run(
            ["sh", "-c", script], check=True, capture_output=True, text=True,
            env={**os.environ, "EXISTING_INSTALL": "true" if existing else "false", "SSH_TARGET": target},
        ).stdout

    def test_local_upgrade_keeps_hostname_and_does_not_offer_reset(self):
        output = self.completion()
        self.assertIn("Detected Pi hostname: message-box-042", output)
        self.assertIn("sudo messageboxctl start", output)
        self.assertNotIn("reset-wifi", output)
        self.assertNotIn("FRESH_INSTALL_FLOW", output)

    def test_remote_upgrade_reuses_the_supplied_account_and_target(self):
        output = self.completion(target="operator@message-box-042.local")
        self.assertIn("ssh -t operator@message-box-042.local sudo messageboxctl start", output)
        self.assertIn("ssh operator@message-box-042.local messageboxctl services", output)
        self.assertNotIn("admin@", output)
        self.assertNotIn("button-box-001", output)

    def test_fresh_install_still_reaches_its_original_handoff(self):
        output = self.completion(existing=False)
        self.assertEqual(output.strip(), "FRESH_INSTALL_FLOW")
