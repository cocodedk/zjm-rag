"""A worktree's .git is a file; the core floor refuses it as the skill's mirror does."""
import unittest

from zjm_rag.copying import _floor_excluded


class GitFileTest(unittest.TestCase):
    def test_a_git_file_is_on_the_floor(self):
        self.assertTrue(_floor_excluded(".git", False, []))
        self.assertTrue(_floor_excluded(".GIT", False, []))


if __name__ == "__main__":
    unittest.main()
