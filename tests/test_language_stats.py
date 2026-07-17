import importlib.util
import sys
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "update_language_stats.py"
SPEC = importlib.util.spec_from_file_location("language_stats", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class RepositorySelectionTests(unittest.TestCase):
    def test_excludes_profile_forks_archived_and_private(self):
        repos = [
            {"full_name": "max/repo", "fork": False, "archived": False, "private": False},
            {"full_name": "max/max", "fork": False, "archived": False, "private": False},
            {"full_name": "max/fork", "fork": True, "archived": False, "private": False},
            {"full_name": "max/old", "fork": False, "archived": True, "private": False},
            {"full_name": "max/private", "fork": False, "archived": False, "private": True},
        ]
        selected = MODULE.select_repositories(repos, {"max/max"})
        self.assertEqual([repo["full_name"] for repo in selected], ["max/repo"])


class SummaryTests(unittest.TestCase):
    def test_sorts_and_calculates_percentages(self):
        rows = MODULE.summarize(
            {"JavaScript": 300, "Python": 100},
            {"JavaScript": {"max/a"}, "Python": {"max/b"}},
            top=6,
        )
        self.assertEqual(rows[0]["language"], "JavaScript")
        self.assertEqual(rows[0]["percentage"], 75.0)
        self.assertEqual(rows[1]["percentage"], 25.0)

    def test_groups_remaining_languages(self):
        rows = MODULE.summarize(
            {"JavaScript": 50, "Python": 30, "SQL": 20},
            {
                "JavaScript": {"max/a"},
                "Python": {"max/b"},
                "SQL": {"max/c"},
            },
            top=2,
        )
        self.assertEqual(rows[-1]["language"], "Outros")
        self.assertEqual(rows[-1]["bytes"], 20)
        self.assertEqual(rows[-1]["percentage"], 20.0)


class RenderTests(unittest.TestCase):
    def test_placeholder_is_clear(self):
        svg = MODULE.render_svg(
            [],
            theme="dark",
            repository_count=0,
            generated_at="25/06/2026",
        )
        self.assertIn("Aguardando a primeira sincronização", svg)
        self.assertIn("Linguagens dos meus projetos", svg)

    def test_renders_percentages_and_segmented_bar(self):
        svg = MODULE.render_svg(
            [
                {"language": "JavaScript", "bytes": 750, "percentage": 75.0, "repositories": 2},
                {"language": "Python", "bytes": 250, "percentage": 25.0, "repositories": 1},
            ],
            theme="dark",
            repository_count=3,
            generated_at="25/06/2026",
        )
        self.assertIn("JavaScript 75.00%", svg)
        self.assertIn("Python 25.00%", svg)
        self.assertIn("3 repositórios", svg)


if __name__ == "__main__":
    unittest.main()
