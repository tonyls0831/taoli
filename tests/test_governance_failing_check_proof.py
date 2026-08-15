"""Intentional failing test for Issue #12 branch-protection evidence.

This branch and pull request must never be merged.
"""

import unittest


class GovernanceFailingCheckProofTest(unittest.TestCase):
    def test_required_checks_block_failure(self) -> None:
        self.fail("intentional Issue #12 branch-protection proof")


if __name__ == "__main__":
    unittest.main()
