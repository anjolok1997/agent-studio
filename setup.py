from setuptools import setup, find_packages

setup(
    name="agent-studio",
    version="0.5.0",
    description="Describe it. A team of AI gets it done.",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="anjolok1997",
    url="https://github.com/anjolok1997/agent-studio",
    packages=find_packages(include=["studio*"]),
    python_requires=">=3.9",
    install_requires=[
        "anthropic>=0.40.0",
        "python-dotenv>=1.0.0",
        "pyyaml>=6.0",
        "websockets>=12.0",
    ],
    extras_require={
        "mcp": ["mcp>=1.0.0"],
    },
    entry_points={
        "console_scripts": [
            "studio=studio.cli:main",
        ],
    },
    include_package_data=True,
    package_data={
        "": ["agents/*.md", "templates/*.yaml", "examples/**/*.yaml"],
    },
)
