import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"


class PythonCompatibilityTest(unittest.TestCase):
    @unittest.skipUnless(
        sys.version_info[:2] == (3, 10),
        "requires the Python 3.10 interpreter used by the CI matrix",
    )
    def test_scripts_compile_on_python_310(self):
        failures = {}

        for path in sorted(SCRIPTS_DIR.glob("*.py")):
            try:
                compile(path.read_text(encoding="utf-8"), str(path), "exec")
            except SyntaxError as exc:
                failures[path.name] = f"{exc.msg} (line {exc.lineno})"

        self.assertEqual(failures, {})


if __name__ == "__main__":
    unittest.main()
