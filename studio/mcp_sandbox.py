"""
MCP Sandbox — Run MCP servers in Docker containers.

Prevents supply chain attacks by:
- Installing npm packages with --ignore-scripts (no postinstall malware)
- Running as non-root user inside the container
- Restricting network access (--network=none for filesystem, explicit for others)
- Mounting only the specific directories/files the server needs
"""

import os
import shutil
import subprocess
from pathlib import Path

BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"

DOCKER_DIR = Path(__file__).resolve().parent.parent / "docker" / "mcp"

# Maps server key -> Docker-specific config
# network: "none" means no internet access (safest), "bridge" allows outbound
# mounts: list of mount specs to add at runtime
# entrypoint: the command inside the container
DOCKER_CONFIGS = {
    "github": {
        "package": "@modelcontextprotocol/server-github",
        "version": "2025.4.8",
        "network": "bridge",  # needs GitHub API access
        "entrypoint": "mcp-server-github",
        "env_passthrough": ["GITHUB_TOKEN"],
    },
    "filesystem": {
        "package": "@modelcontextprotocol/server-filesystem",
        "version": "2026.1.14",
        "network": "none",  # no internet needed
        "entrypoint": "mcp-server-filesystem",
        "env_passthrough": [],
        "needs_mount": True,  # user specifies a directory to mount
    },
    "postgres": {
        "package": "@modelcontextprotocol/server-postgres",
        "version": "0.6.2",
        "network": "bridge",  # needs database access
        "entrypoint": "mcp-server-postgres",
        "env_passthrough": ["DATABASE_URL"],
    },
    "slack": {
        "package": "@modelcontextprotocol/server-slack",
        "version": "2025.4.25",
        "network": "bridge",  # needs Slack API access
        "entrypoint": "mcp-server-slack",
        "env_passthrough": ["SLACK_BOT_TOKEN"],
    },
    "puppeteer": {
        "package": "@modelcontextprotocol/server-puppeteer",
        "version": "2025.5.12",
        "network": "bridge",  # needs web access
        "entrypoint": "mcp-server-puppeteer",
        "env_passthrough": [],
    },
    "redis": {
        "package": "@modelcontextprotocol/server-redis",
        "version": "2025.4.25",
        "network": "bridge",  # needs Redis access
        "entrypoint": "mcp-server-redis",
        "env_passthrough": ["REDIS_URL"],
    },
}


def docker_available() -> bool:
    """Check if Docker is installed and running."""
    return shutil.which("docker") is not None


def image_name(server_key: str) -> str:
    """Docker image name for a curated MCP server."""
    return f"agent-studio-mcp-{server_key}"


def image_exists(server_key: str) -> bool:
    """Check if the Docker image is already built."""
    result = subprocess.run(
        ["docker", "image", "inspect", image_name(server_key)],
        capture_output=True,
    )
    return result.returncode == 0


def build_image(server_key: str) -> bool:
    """Build the Docker image for a curated MCP server."""
    config = DOCKER_CONFIGS.get(server_key)
    if not config:
        print(f"  {RED}No Docker config for '{server_key}'.{RESET}")
        return False

    dockerfile = DOCKER_DIR / "Dockerfile.base"
    if not dockerfile.exists():
        print(f"  {RED}Dockerfile not found: {dockerfile}{RESET}")
        return False

    tag = image_name(server_key)
    print(f"  {DIM}Building Docker image for {server_key}...{RESET}")

    result = subprocess.run(
        [
            "docker", "build",
            "-f", str(dockerfile),
            "--build-arg", f"MCP_PACKAGE={config['package']}",
            "--build-arg", f"MCP_VERSION={config['version']}",
            "-t", tag,
            str(DOCKER_DIR),
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"  {RED}Docker build failed:{RESET}")
        print(f"  {result.stderr[:500]}")
        return False

    print(f"  {GREEN}Built {tag}{RESET}")
    return True


def get_docker_command(server_key: str, server_config: dict) -> list[str]:
    """
    Build the `docker run` command for an MCP server.

    Returns the full command list that replaces the bare `npx` command
    in the MCP bridge's stdio transport.
    """
    config = DOCKER_CONFIGS.get(server_key)
    if not config:
        return None

    tag = image_name(server_key)

    cmd = [
        "docker", "run",
        "--rm",                         # clean up after exit
        "-i",                           # stdin for stdio transport
        f"--network={config['network']}",
        "--read-only",                  # read-only filesystem
        "--tmpfs", "/tmp",              # writable tmp only
        "--cap-drop=ALL",               # drop all Linux capabilities
        "--security-opt=no-new-privileges",
    ]

    # Pass through only the env vars the server needs
    env = server_config.get("env", {})
    for var in config.get("env_passthrough", []):
        if var in env:
            cmd.extend(["-e", f"{var}={env[var]}"])

    # Mount directories if needed (e.g. filesystem server)
    if config.get("needs_mount"):
        # The last arg in the server config is the directory path
        args = server_config.get("args", [])
        for arg in args:
            if arg.startswith("/") and os.path.isdir(arg):
                cmd.extend(["-v", f"{arg}:/data:ro"])

    cmd.extend([tag, config["entrypoint"]])

    # Add any extra args (e.g. /data for filesystem)
    if config.get("needs_mount"):
        cmd.append("/data")

    return cmd


def ensure_image(server_key: str) -> bool:
    """Build the image if it doesn't exist. Returns True if ready."""
    if image_exists(server_key):
        return True
    return build_image(server_key)
