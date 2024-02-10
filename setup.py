import pathlib

from setuptools import find_packages, setup

here = pathlib.Path(__file__).parent.resolve()

# Get the long description from the README file
long_description = (here / "README.md").read_text(encoding="utf-8")

setup(
    name="rockset-stacky",
    version="1.0.12",
    description="""
    stacky is a tool to manage stacks of PRs. This allows developers to easily 
    manage many smaller, more targeted PRs that depend on each other.
    """,
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/rockset/stacky",
    author="Rockset",
    author_email="tudor@rockset.com",
    keywords="github, stack, pr, pull request",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.8, <4",
    install_requires=["asciitree", "ansicolors", "simple-term-menu"],
    entry_points={
        "console_scripts": [
            "stacky=stacky:main",
        ],
    },
    project_urls={
        "Bug Reports": "https://github.com/rockset/stacky/issues",
        "Source": "https://github.com/rockset/stacky",
    },
)
