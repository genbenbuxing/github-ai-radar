from setuptools import find_packages, setup


setup(
    name="github-ai-radar",
    version="0.4.1",
    description="Local GitHub AI project radar with audited daily reports",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    package_dir={"": "src"},
    packages=find_packages("src"),
    python_requires=">=3.9",
    entry_points={
        "console_scripts": [
            "github-ai-radar=github_ai_radar.cli:main",
        ],
    },
)
