"""
provtrack setup.py
~~~~~~~~~~~~~~~~~~
pip install provtrack
"""

from pathlib import Path
import setuptools

long_description = (Path(__file__).parent / "README.md").read_text(encoding="utf-8")

setuptools.setup(
    name="provtrack",
    version="2.0.0",
    description=(
        "Zero-instrumentation ML pipeline provenance tracking. "
        "One line of code. Full data lineage."
    ),
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Princess",
    author_email="priyankatiwari140419@gmail.com",
    url="https://github.com/Princess0407/provtrack",
    project_urls={
        "Bug Tracker": "https://github.com/Princess0407/provtrack/issues",
        "Documentation": "https://github.com/Princess0407/provtrack/blob/main/README.md",
        "Source Code": "https://github.com/Princess0407/provtrack",
    },
    license="Apache-2.0",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    keywords=[
        "ml",
        "mlops",
        "data lineage",
        "provenance",
        "pandas",
        "sklearn",
        "data pipeline",
        "observability",
        "reproducibility",
    ],
    packages=setuptools.find_packages(exclude=["tests*", "docs*"]),
    python_requires=">=3.8",
    install_requires=[
        "pandas>=1.3.0",
        "networkx>=2.6",
        "textual>=0.47.0",
        "pyperclip>=1.8.0",
    ],
    extras_require={
        "sklearn": ["scikit-learn>=0.24"],
        "serve": ["fastapi>=0.100.0", "uvicorn>=0.20.0"],
        "postgres": ["psycopg2-binary>=2.9.0"],
        "s3": ["boto3>=1.20.0"],
        "dev": [
            "pytest>=7.0",
            "pytest-cov>=4.0",
            "scikit-learn>=0.24",
            "numpy>=1.21",
            "fastapi",
            "uvicorn",
        ],
        "viz": [
            "matplotlib>=3.4",
        ],
    },
    entry_points={
        "console_scripts": [
            "provtrack=provtrack.cli:main",
        ],
    },
    include_package_data=True,
)
