"""The skill's zjm-project wrapper refuses folders zjm must never index, before it calls zjm."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "skills/zjm-rag/scripts/zjm-project"


class SkillTest(unittest.TestCase):
    def test_refuses_a_folder_inside_a_floor_folder_in_any_case(self):
        for floor in (".aws", ".AWS", "Node_Modules"):
            with tempfile.TemporaryDirectory() as tmp:
                docs = Path(tmp) / floor / "docs"
                docs.mkdir(parents=True)
                r = subprocess.run([shutil.which("bash"), str(SCRIPT), "reindex", "t", str(docs)],
                                   capture_output=True, text=True, check=False, timeout=30)
                self.assertEqual(r.returncode, 2, floor)
                self.assertIn("never indexes", r.stderr)


if __name__ == "__main__":
    unittest.main()
