from setuptools import find_packages, setup


setup(
    name="github-ai-radar",
    version="0.4.0",
    description="Local AI application, high-tech finance, and AI biopharma radar with audited daily reports",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    package_dir={"": "src"},
    packages=find_packages("src"),
    python_requires=">=3.9",
    install_requires=[
        "tomli-w>=1.0",
        "tomli>=2.0; python_version < '3.11'",
    ],
    entry_points={
        "console_scripts": [
            "github-ai-radar=github_ai_radar.cli:main",
        ],
    },
)
