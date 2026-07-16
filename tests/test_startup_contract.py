import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class StartupContractTest(unittest.TestCase):
    def test_shell_script_builds_vue_before_python(self):
        script = (ROOT / "start.sh").read_text(encoding="utf-8")
        self.assertIn("set -e", script)
        self.assertIn("frontend/node_modules", script)
        self.assertIn("./install-deps.sh", script)
        self.assertIn(".course-agent-deps-ready", script)
        self.assertIn("npm run build --prefix frontend", script)
        self.assertLess(script.index("npm run build"), script.index(".venv/bin/python run.py"))
        self.assertIn("20.19", script)
        self.assertIn("22.12", script)
        self.assertIn("sys.version_info >= (3, 9)", script)

    def test_batch_script_builds_vue_before_python(self):
        script = (ROOT / "start.bat").read_text(encoding="utf-8")
        self.assertIn("frontend\\node_modules", script)
        self.assertIn("install-deps.bat", script)
        self.assertIn(".course-agent-deps-ready", script)
        self.assertIn("npm run build --prefix frontend", script)
        self.assertIn("if errorlevel 1 exit /b 1", script.lower())
        self.assertLess(script.index("npm run build"), script.index("run.py"))
        self.assertIn("20.19", script)
        self.assertIn("22.12", script)
        self.assertIn("sys.version_info >= (3, 9)", script)

    def test_dependency_installers_cover_python_and_node_packages(self):
        shell = (ROOT / "install-deps.sh").read_text(encoding="utf-8")
        batch = (ROOT / "install-deps.bat").read_text(encoding="utf-8")
        for script in (shell, batch):
            self.assertIn("requirements.txt", script)
            self.assertIn("package-lock.json", script)
            self.assertIn("npm ci --prefix frontend --include=dev", script)
            self.assertIn(".venv", script)
            self.assertIn(".course-agent-deps-ready", script)
            self.assertIn("20.19", script)
            self.assertIn("22.12", script)

    def test_readme_documents_vue_and_both_startup_paths(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for text in (
            "Vue 3",
            "Node.js 20.19",
            "start.bat",
            "start.sh",
            "install-deps.bat",
            "install-deps.sh",
            "npm run dev --prefix frontend",
            "web/dist",
        ):
            self.assertIn(text, readme)


if __name__ == "__main__":
    unittest.main()
