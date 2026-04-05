"""
Project scanner for the Claude Code review workflow.

Scans a target project directory, collects relevant files, and generates
structured context that the orchestrator pipeline can process.

Usage from Claude Code:
    from orchestrator.review import scan_project, generate_review_prompt
    context = scan_project("/path/to/project")
    prompt = generate_review_prompt(context, focus="security")
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

# File extensions to include in review
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".rb",
    ".c", ".cpp", ".h", ".hpp", ".cs", ".swift", ".kt", ".scala",
    ".php", ".sh", ".bash", ".zsh",
}

CONFIG_EXTENSIONS = {
    ".toml", ".yaml", ".yml", ".json", ".ini", ".cfg", ".conf",
    ".env.example", ".gitignore", ".dockerignore",
}

DOC_NAMES = {
    "README.md", "README.rst", "README.txt", "CHANGELOG.md",
    "CONTRIBUTING.md", "LICENSE", "Makefile", "Dockerfile",
    "docker-compose.yml", "docker-compose.yaml",
}

# Directories to always skip
SKIP_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", "node_modules", ".venv", "venv",
    "env", ".env", ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "dist", "build", ".eggs", "*.egg-info", ".next", ".nuxt", "coverage",
    "htmlcov", ".terraform", ".gradle", "target",
}

MAX_FILE_SIZE = 100_000  # 100KB per file
MAX_TOTAL_FILES = 200


@dataclass
class FileInfo:
    path: str          # relative to project root
    extension: str
    size: int
    content: str
    category: str      # "code", "config", "doc", "test"


@dataclass
class ProjectContext:
    root: str
    files: list[FileInfo] = field(default_factory=list)
    tree: str = ""
    language_stats: dict[str, int] = field(default_factory=dict)
    total_lines: int = 0
    has_tests: bool = False
    has_ci: bool = False
    has_docker: bool = False
    config_files: list[str] = field(default_factory=list)


def _should_skip_dir(name: str) -> bool:
    return name in SKIP_DIRS or name.startswith(".")


def _categorize_file(rel_path: str, ext: str) -> str | None:
    name = os.path.basename(rel_path)
    lower_path = rel_path.lower()

    if name in DOC_NAMES:
        return "doc"
    if "test" in lower_path or "spec" in lower_path:
        if ext in CODE_EXTENSIONS:
            return "test"
    if ext in CODE_EXTENSIONS:
        return "code"
    if ext in CONFIG_EXTENSIONS:
        return "config"
    if name in DOC_NAMES:
        return "doc"
    return None


def scan_project(project_path: str, max_files: int = MAX_TOTAL_FILES) -> ProjectContext:
    """Scan a project directory and collect file contents and metadata."""
    root = Path(project_path).resolve()
    if not root.is_dir():
        raise ValueError(f"Not a directory: {root}")

    ctx = ProjectContext(root=str(root))
    tree_lines = []
    file_count = 0

    for dirpath, dirnames, filenames in os.walk(root):
        # Filter out skip directories in-place
        dirnames[:] = sorted(d for d in dirnames if not _should_skip_dir(d))

        rel_dir = os.path.relpath(dirpath, root)
        depth = 0 if rel_dir == "." else rel_dir.count(os.sep) + 1

        if rel_dir != ".":
            tree_lines.append(f"{'  ' * (depth - 1)}{os.path.basename(dirpath)}/")

        for fname in sorted(filenames):
            if file_count >= max_files:
                break

            fpath = Path(dirpath) / fname
            rel_path = fpath.relative_to(root).as_posix()
            ext = fpath.suffix.lower()

            category = _categorize_file(rel_path, ext)
            if category is None:
                continue

            tree_lines.append(f"{'  ' * depth}{fname}")

            # Read file content
            size = fpath.stat().st_size
            if size > MAX_FILE_SIZE:
                content = f"[File too large: {size} bytes, skipped]"
            else:
                try:
                    content = fpath.read_text(errors="replace")
                except Exception:
                    content = "[Could not read file]"

            info = FileInfo(
                path=rel_path,
                extension=ext,
                size=size,
                content=content,
                category=category,
            )
            ctx.files.append(info)
            file_count += 1

            # Stats
            if category in ("code", "test"):
                lang = ext.lstrip(".")
                ctx.language_stats[lang] = ctx.language_stats.get(lang, 0) + 1
                ctx.total_lines += content.count("\n") + 1
            if category == "test":
                ctx.has_tests = True

    ctx.tree = "\n".join(tree_lines)

    # Detect CI and Docker
    config_names = {f.path for f in ctx.files if f.category == "config"}
    file_names = {os.path.basename(f.path) for f in ctx.files}
    ctx.has_ci = any(
        ".github/workflows" in p or ".gitlab-ci" in p or "Jenkinsfile" in p
        for p in config_names
    )
    ctx.has_docker = "Dockerfile" in file_names or "docker-compose.yml" in file_names
    ctx.config_files = sorted(f.path for f in ctx.files if f.category == "config")

    return ctx


def generate_review_prompt(
    ctx: ProjectContext,
    focus: str = "general",
    files: list[str] | None = None,
) -> dict[str, str]:
    """Generate structured prompts for each pipeline stage.

    Returns a dict with keys for each agent stage:
        - acquisition: project context summary
        - architect: architecture review prompt
        - qa_architecture: QA risk assessment prompt for architecture
        - developer: code review prompt
        - qa_code: QA risk assessment prompt for code
        - reporting: final report generation prompt
        - verification: how to know the changes will work

    Args:
        ctx: ProjectContext from scan_project()
        focus: Review focus area ("security", "performance", "quality", "general")
        files: Optional list of specific file paths to focus on
    """
    # Filter to specific files if requested
    review_files = ctx.files
    if files:
        review_files = [f for f in ctx.files if f.path in files]

    code_files = [f for f in review_files if f.category == "code"]
    test_files = [f for f in review_files if f.category == "test"]
    config_files = [f for f in review_files if f.category == "config"]

    # Build file content blocks
    code_block = "\n\n".join(
        f"### {f.path}\n```{f.extension.lstrip('.')}\n{f.content}\n```"
        for f in code_files
    )
    test_block = "\n\n".join(
        f"### {f.path}\n```{f.extension.lstrip('.')}\n{f.content}\n```"
        for f in test_files
    )
    config_block = "\n\n".join(
        f"### {f.path}\n```\n{f.content}\n```"
        for f in config_files
    )

    focus_instructions = {
        "general": "Review for overall code quality, maintainability, and correctness.",
        "security": (
            "Focus on security vulnerabilities: injection, auth issues, data exposure, "
            "insecure defaults, missing input validation, OWASP Top 10."
        ),
        "performance": (
            "Focus on performance: N+1 queries, unnecessary allocations, blocking calls, "
            "missing caching, algorithmic complexity, resource leaks."
        ),
        "quality": (
            "Focus on code quality: DRY violations, unclear naming, missing error handling, "
            "dead code, overly complex functions, test coverage gaps."
        ),
    }
    focus_text = focus_instructions.get(focus, focus_instructions["general"])

    # Language summary
    lang_summary = ", ".join(
        f"{ext} ({count} files)" for ext, count in sorted(ctx.language_stats.items())
    )

    prompts = {}

    # Stage 1: Data Acquisition (project context)
    prompts["acquisition"] = f"""## Project Context

**Root:** {ctx.root}
**Languages:** {lang_summary}
**Total lines:** {ctx.total_lines}
**Has tests:** {ctx.has_tests}
**Has CI:** {ctx.has_ci}
**Has Docker:** {ctx.has_docker}
**Config files:** {', '.join(ctx.config_files) or 'none'}

### Project Structure
```
{ctx.tree}
```

### Review Focus
{focus_text}

### Configuration Files
{config_block or '_No config files found._'}

Summarize the project: what it does, what technologies it uses, and what the key areas of concern are given the review focus."""

    # Stage 2: Architecture Review
    prompts["architect"] = f"""## Architecture Review

Review the architecture of this project. The project structure is:
```
{ctx.tree}
```

### Source Files
{code_block or '_No code files found._'}

### Review Focus
{focus_text}

Analyze:
1. Overall architecture and design patterns used
2. Module organization and separation of concerns
3. Dependency management and coupling between components
4. Error handling strategy
5. Areas that could be improved

Provide specific file references (file:line) for each finding."""

    # Stage 3: QA Architecture Risk Assessment
    prompts["qa_architecture"] = f"""## QA: Architecture Risk Assessment

Given the architecture review above, assess risks:

### Review Focus
{focus_text}

For each risk found, provide:
1. **Description**: What the risk is
2. **Severity**: HIGH / MEDIUM / LOW
3. **Location**: Specific files and lines affected
4. **Recommendation**: How to fix it

HIGH severity risks are blocking and must be addressed.
MEDIUM risks should be addressed.
LOW risks are noted for future improvement.

Format each risk as:
- **[SEVERITY]** description (file:line) — recommendation"""

    # Stage 4: Code Review
    prompts["developer"] = f"""## Code Review

Review the following code files for issues:

### Review Focus
{focus_text}

### Source Files
{code_block or '_No code files found._'}

### Test Files
{test_block or '_No test files found._'}

For each issue found, provide:
1. The file path and line number
2. What the issue is
3. A concrete fix (show the corrected code)

Focus on actionable improvements. Don't flag style preferences — only flag things that are bugs, security issues, or clearly wrong.

### Documentation Review
Also review whether the project documentation (README, ARCHITECTURE.md, CLAUDE.md, \
inline docstrings) accurately reflects the current code. Flag any gaps as findings and \
provide the updated content."""

    # Stage 5: QA Code Risk Assessment
    prompts["qa_code"] = f"""## QA: Code Risk Assessment

Given the code review above, assess risks and generate test cases:

### Review Focus
{focus_text}

For each risk:
- **[SEVERITY]** description (file:line) — recommendation

Also flag any documentation that is outdated or missing relative to the code changes:
- **[MEDIUM]** Documentation gap: description — what docs need updating

Then generate test cases that would catch the identified risks.
Format tests as code blocks that could be added to the project."""

    # Stage 6: Reporting
    prompts["reporting"] = f"""## Final Report

Compile all findings into a structured report:

1. **Executive Summary**: 2-3 sentence overview
2. **Architecture Findings**: Key architectural issues and recommendations
3. **Code Findings**: Specific bugs, vulnerabilities, or quality issues with file:line references
4. **Risk Assessment**: All risks ranked by severity
5. **Suggested Fixes**: Concrete code changes (as diffs or code blocks)
6. **Test Gaps**: Missing test coverage and suggested test cases
7. **Documentation Updates**: List every doc file that must be created or updated, \
with the section and revised content
8. **Action Items**: Prioritized list of next steps

Focus on actionable items. Every finding should have a specific file reference and a concrete recommendation."""

    # Stage 7: Verification — how to know the changes will work
    prompts["verification"] = f"""## How to Know the Changes Will Work

Based on the findings and recommended changes above, provide a concrete verification \
checklist the user can follow to confirm the changes are working correctly.

### Include:
1. **Commands to run**: exact shell commands (e.g. test suites, linters, build steps)
2. **What to observe**: specific output, log lines, or metrics that confirm success
3. **Manual checks**: any steps that require human judgement (e.g. reviewing a log stream)
4. **Regression signals**: what would indicate the change broke something

### Guidelines:
- Be specific: "run `pytest tests/ -v` and confirm 0 failures" not "run the tests"
- For observability changes: show how to tail logs, what JSON fields to look for, \
example event payloads
- For API changes: show a curl/httpie command or Python snippet to exercise the endpoint
- For config changes: show how to verify the config is loaded correctly
- Keep it short — a user should be able to follow this in under 5 minutes"""

    return prompts


def format_review_for_claude_code(
    ctx: ProjectContext,
    focus: str = "general",
    files: list[str] | None = None,
) -> str:
    """Generate a single structured document for Claude Code to process.

    This is the main entry point for Claude Code integration. It produces
    a step-by-step review document that Claude Code follows as a workflow.
    """
    prompts = generate_review_prompt(ctx, focus=focus, files=files)

    sections = [
        "# Orchestrator Review Pipeline",
        "",
        "Follow each stage below in order. Complete each stage fully before "
        "moving to the next. If a QA stage finds HIGH severity risks, go back "
        "and revise the previous stage's findings before continuing.",
        "",
        "---",
        "",
        "# Stage 1: Data Acquisition",
        prompts["acquisition"],
        "",
        "---",
        "",
        "# Stage 2: Architecture Review",
        prompts["architect"],
        "",
        "---",
        "",
        "# Stage 3: QA Architecture Risk Assessment",
        prompts["qa_architecture"],
        "",
        "---",
        "",
        "# Stage 4: Code Review",
        prompts["developer"],
        "",
        "---",
        "",
        "# Stage 5: QA Code Risk Assessment",
        prompts["qa_code"],
        "",
        "---",
        "",
        "# Stage 6: Final Report",
        prompts["reporting"],
        "",
        "---",
        "",
        "# Stage 7: How to Know the Changes Will Work",
        prompts["verification"],
    ]

    return "\n".join(sections)
