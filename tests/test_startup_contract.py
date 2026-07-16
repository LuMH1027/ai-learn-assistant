import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class StartupContractTest(unittest.TestCase):
    def test_shell_script_builds_vue_before_python(self):
        script = (ROOT / "start.sh").read_text(encoding="utf-8")
        self.assertIn("set -e", script)
        self.assertIn("frontend/node_modules", script)
        self.assertIn("npm ci --prefix frontend", script)
        self.assertIn("npm run build --prefix frontend", script)
        self.assertLess(script.index("npm run build"), script.index("python3 run.py"))
        self.assertIn("20.19", script)
        self.assertIn("22.12", script)
        self.assertIn("sys.version_info >= (3, 9)", script)

    def test_batch_script_builds_vue_before_python(self):
        script = (ROOT / "start.bat").read_text(encoding="utf-8")
        self.assertIn("frontend\\node_modules", script)
        self.assertIn("npm ci --prefix frontend", script)
        self.assertIn("npm run build --prefix frontend", script)
        self.assertIn("if errorlevel 1 exit /b 1", script.lower())
        self.assertLess(script.index("npm run build"), script.index("run.py"))
        self.assertIn("20.19", script)
        self.assertIn("22.12", script)
        self.assertIn("sys.version_info >= (3, 9)", script)

    def test_readme_documents_vue_and_both_startup_paths(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for text in (
            "Vue 3",
            "Node.js 20.19",
            "start.bat",
            "start.sh",
            "npm run dev --prefix frontend",
            "web/dist",
        ):
            self.assertIn(text, readme)


if __name__ == "__main__":
    unittest.main()
