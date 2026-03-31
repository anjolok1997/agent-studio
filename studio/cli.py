"""
Agent Studio CLI — entry point for the `studio` command.

After installing with `pip install agent-studio`, just type:
    studio                                    # interactive
    studio "summarize my project docs"        # one-shot
    studio schedule list                      # manage recurring tasks
"""

import sys
from pathlib import Path


def _ensure_data_dirs():
    """Ensure agents/, templates/, examples/ are accessible.

    When installed as a package, these ship with the package.
    When running from source, they're in the project root.
    """
    # Check if we're running from source (launch.py exists alongside)
    source_root = Path(__file__).resolve().parent.parent
    if (source_root / "launch.py").exists():
        return source_root

    # Installed as a package — use package data location
    return source_root


def main():
    """Entry point for the `studio` command."""
    # Add the project root to path so launch.py imports work
    root = _ensure_data_dirs()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    # Import and run the main launcher
    from launch import main as launch_main
    launch_main()


if __name__ == "__main__":
    main()
