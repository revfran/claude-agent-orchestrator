import os
import tempfile

import pytest

from orchestrator.ci import build_structural_report, get_pr_changed_files


@pytest.fixture
def sample_project(tmp_path):
    """Create a sample project with various risk patterns."""
    src = tmp_path / "src"
    src.mkdir()

    # File with security issues
    (src / "unsafe.py").write_text(
        "import os\n"
        "def run(cmd):\n"
        "    os.system(cmd)\n"
        "\n"
        "def compute(expr):\n"
        "    return eval(expr)\n"
        "\n"
        "password = 'hunter2'\n"
    )

    # File with quality issues
    (src / "messy.py").write_text(
        "from os import *\n"
        "\n"
        "def handle():\n"
        "    try:\n"
        "        do_stuff()\n"
        "    except:\n"
        "        pass\n"
        "\n"
        "# TODO: fix this later\n"
    )

    # Clean file
    (src / "clean.py").write_text(
        "def add(a: int, b: int) -> int:\n"
        "    return a + b\n"
    )

    # Config
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "test"\n'
    )

    return tmp_path


def test_structural_report_general(sample_project):
    report = build_structural_report(str(sample_project), "general", [])

    assert "## Orchestrator Review Report" in report
    assert "### Project Overview" in report
    assert "### Risk Assessment" in report
    assert "Claude Agent Orchestrator" in report


def test_structural_report_detects_security_risks(sample_project):
    report = build_structural_report(str(sample_project), "security", [])

    assert "[HIGH]" in report
    assert "command injection" in report.lower() or "eval()" in report
    assert "password" in report.lower()


def test_structural_report_detects_quality_risks(sample_project):
    report = build_structural_report(str(sample_project), "quality", [])

    assert "bare `except:`" in report or "except:" in report
    assert "wildcard import" in report or "import *" in report


def test_structural_report_with_changed_files(sample_project):
    report = build_structural_report(
        str(sample_project), "security", ["src/clean.py"]
    )

    assert "### Files Reviewed" in report
    assert "src/clean.py" in report
    # Should NOT find risks in clean.py
    assert "[HIGH]" not in report


def test_structural_report_no_code_risks_in_clean_project(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("def main():\n    print('hello')\n")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_main.py").write_text("def test_main():\n    assert True\n")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "clean"\n')

    report = build_structural_report(str(tmp_path), "general", [])
    assert "[HIGH]" not in report


def test_structural_report_focus_label(sample_project):
    for focus in ("general", "security", "performance", "quality"):
        report = build_structural_report(str(sample_project), focus, [])
        assert f"Focus: {focus}" in report


def test_get_pr_changed_files_nonexistent():
    # Should return empty list for non-git directory
    files = get_pr_changed_files("/tmp")
    assert files == []
