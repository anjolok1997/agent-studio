"""
Project Builder — Extract code from worker output into real project files.

When workers produce code blocks tagged with filenames, this module
extracts them into a real project directory structure.

Workers output code like:
    FILE: src/app.py
    ```python
    from flask import Flask
    app = Flask(__name__)
    ...
    ```

    FILE: requirements.txt
    ```
    flask==3.0
    ```

This module parses those blocks and creates the actual files.
"""

from __future__ import annotations

import re
from pathlib import Path


BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
GREEN = "\033[32m"
CYAN = "\033[36m"
YELLOW = "\033[33m"

# Match: FILE: path/to/file.ext followed by a code block
FILE_BLOCK_PATTERN = re.compile(
    r"FILE:\s*([^\n`]+)\s*\n"       # FILE: path/to/file
    r"```[^\n]*\n"                   # ```language
    r"(.*?)"                         # content
    r"\n```",                        # closing ```
    re.DOTALL,
)

# Dangerous paths to block
BLOCKED_PATTERNS = [
    "..", "~", "$", "/etc", "/usr", "/bin", "/var",
    ".env", "credentials", "secret", "token", ".ssh",
]


def _is_safe_path(filepath: str) -> bool:
    """Block paths that could escape the project directory."""
    for pattern in BLOCKED_PATTERNS:
        if pattern in filepath.lower():
            return False
    if filepath.startswith("/"):
        return False
    return True


def extract_files(artifacts: list[dict]) -> list[dict]:
    """Extract FILE: blocks from all artifacts.

    Returns list of {"path": str, "content": str, "agent": str}.
    """
    files = []
    for artifact in artifacts:
        content = artifact.get("content", "")
        agent = artifact.get("agent", "unknown")

        for match in FILE_BLOCK_PATTERN.finditer(content):
            filepath = match.group(1).strip()
            file_content = match.group(2)

            if _is_safe_path(filepath):
                files.append({
                    "path": filepath,
                    "content": file_content,
                    "agent": agent,
                })

    return files


def build_project(files: list[dict], project_dir: Path) -> list[Path]:
    """Write extracted files to a project directory.

    Returns list of created file paths. Markdown docs also get a PDF version.
    """
    created = []
    project_dir.mkdir(parents=True, exist_ok=True)

    for f in files:
        filepath = project_dir / f["path"]

        # Create parent directories
        filepath.parent.mkdir(parents=True, exist_ok=True)

        # Write the file
        filepath.write_text(f["content"])
        created.append(filepath)

        # Auto-generate PDF for markdown documents
        if filepath.suffix == ".md":
            try:
                from .pdf_export import markdown_to_pdf
                pdf_path = filepath.with_suffix(".pdf")
                title = filepath.stem.replace("-", " ").replace("_", " ").title()
                markdown_to_pdf(f["content"], pdf_path, title=title)
                created.append(pdf_path)
            except ImportError:
                pass  # fpdf2 not installed, skip PDF
            except Exception:
                pass  # PDF generation failed, still have the .md

    return created


def display_project(created: list[Path], project_dir: Path):
    """Show the created project structure."""
    if not created:
        return

    print(f"\n  {GREEN}{'─' * 56}{RESET}")
    print(f"  {BOLD}Project created: {project_dir}{RESET}")
    print(f"  {GREEN}{'─' * 56}{RESET}")

    # Group by directory
    for filepath in sorted(created):
        relative = filepath.relative_to(project_dir)
        indent = "  " * (len(relative.parts) - 1)
        print(f"    {indent}{CYAN}{relative.name}{RESET}")

    print(f"\n  {DIM}{len(created)} files created{RESET}")
    print(f"  {DIM}cd {project_dir}{RESET}\n")


def process_artifacts(artifacts: list[dict], output_dir: Path = None) -> tuple[list[Path], list[dict]]:
    """Main entry point. Extract project files from artifacts.

    Returns (created_files, remaining_artifacts).
    Remaining artifacts are those that didn't contain FILE: blocks.
    """
    files = extract_files(artifacts)

    if not files:
        return [], artifacts

    # Create project directory
    if output_dir is None:
        output_dir = Path("output/project")
    project_dir = output_dir

    created = build_project(files, project_dir)
    display_project(created, project_dir)

    # Figure out which artifacts had files extracted vs pure text
    artifacts_with_files = set()
    for f in files:
        artifacts_with_files.add(f["agent"])

    remaining = [a for a in artifacts if a["agent"] not in artifacts_with_files]

    return created, remaining
