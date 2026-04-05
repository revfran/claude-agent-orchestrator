import os
import tempfile

import pytest

from orchestrator.review import (
    ProjectContext,
    scan_project,
    generate_review_prompt,
    format_review_for_claude_code,
)


@pytest.fixture
def sample_project(tmp_path):
    """Create a small sample project for testing."""
    # Source code
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("def main():\n    print('hello')\n")
    (src / "auth.py").write_text(
        "import os\n\ndef get_token():\n    return os.environ['TOKEN']\n"
    )

    # Tests
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_main.py").write_text(
        "def test_main():\n    assert True\n"
    )

    # Config
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "sample"\nversion = "0.1.0"\n'
    )
    (tmp_path / ".gitignore").write_text("__pycache__/\n.venv/\n")

    # README
    (tmp_path / "README.md").write_text("# Sample Project\n")

    # Directories that should be skipped
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("git config")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "pkg.js").write_text("module.exports = {}")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "main.cpython-311.pyc").write_bytes(b"\x00")

    return tmp_path


def test_scan_project(sample_project):
    ctx = scan_project(str(sample_project))

    assert isinstance(ctx, ProjectContext)
    assert ctx.root == str(sample_project)
    assert len(ctx.files) > 0

    file_paths = {f.path for f in ctx.files}
    assert "src/main.py" in file_paths
    assert "src/auth.py" in file_paths
    assert "tests/test_main.py" in file_paths
    assert "pyproject.toml" in file_paths
    assert "README.md" in file_paths


def test_scan_skips_hidden_and_vendor_dirs(sample_project):
    ctx = scan_project(str(sample_project))
    file_paths = {f.path for f in ctx.files}

    # Should NOT contain files from skipped directories
    assert not any(".git/" in p for p in file_paths)
    assert not any("node_modules/" in p for p in file_paths)
    assert not any("__pycache__/" in p for p in file_paths)


def test_scan_categorizes_files(sample_project):
    ctx = scan_project(str(sample_project))

    categories = {f.path: f.category for f in ctx.files}
    assert categories.get("src/main.py") == "code"
    assert categories.get("src/auth.py") == "code"
    assert categories.get("tests/test_main.py") == "test"
    assert categories.get("pyproject.toml") == "config"
    assert categories.get("README.md") == "doc"


def test_scan_detects_project_features(sample_project):
    ctx = scan_project(str(sample_project))

    assert ctx.has_tests is True
    assert ctx.total_lines > 0
    assert "py" in ctx.language_stats


def test_scan_invalid_path():
    with pytest.raises(ValueError, match="Not a directory"):
        scan_project("/nonexistent/path")


def test_scan_respects_max_files(sample_project):
    ctx = scan_project(str(sample_project), max_files=2)
    assert len(ctx.files) == 2


def test_generate_review_prompt(sample_project):
    ctx = scan_project(str(sample_project))
    prompts = generate_review_prompt(ctx, focus="security")

    # All 6 stages should be present
    assert "acquisition" in prompts
    assert "architect" in prompts
    assert "qa_architecture" in prompts
    assert "developer" in prompts
    assert "qa_code" in prompts
    assert "reporting" in prompts

    # Acquisition should contain project info
    assert "py" in prompts["acquisition"]
    assert str(sample_project) in prompts["acquisition"]

    # Security focus should be reflected
    assert "security" in prompts["developer"].lower() or "vulnerab" in prompts["developer"].lower()


def test_generate_review_prompt_specific_files(sample_project):
    ctx = scan_project(str(sample_project))
    prompts = generate_review_prompt(ctx, files=["src/auth.py"])

    # Should include auth.py content in the code review
    assert "auth.py" in prompts["developer"]
    assert "get_token" in prompts["developer"]


def test_format_review_for_claude_code(sample_project):
    ctx = scan_project(str(sample_project))
    review = format_review_for_claude_code(ctx, focus="general")

    assert "# Orchestrator Review Pipeline" in review
    assert "Stage 1: Data Acquisition" in review
    assert "Stage 2: Architecture Review" in review
    assert "Stage 3: QA Architecture Risk Assessment" in review
    assert "Stage 4: Code Review" in review
    assert "Stage 5: QA Code Risk Assessment" in review
    assert "Stage 6: Final Report" in review

    # Should contain actual file content
    assert "def main():" in review


def test_large_file_skipped(tmp_path):
    """Files over MAX_FILE_SIZE should be skipped with a note."""
    src = tmp_path / "src"
    src.mkdir()
    # Create a file just over the limit
    (src / "big.py").write_text("x = 1\n" * 20000)

    ctx = scan_project(str(tmp_path))
    big_files = [f for f in ctx.files if f.path == "src/big.py"]
    assert len(big_files) == 1
    assert "too large" in big_files[0].content.lower() or len(big_files[0].content) < 200000
