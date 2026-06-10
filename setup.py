from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="contract-retriever",
    version="1.0.0",
    author="Contract Retriever Team",
    description="合同条款快速检索与比对命令行工具",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/your-org/contract-retriever",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Legal Industry",
        "Intended Audience :: Developers",
        "Topic :: Office/Business :: Legal",
        "Topic :: Text Processing :: Indexing",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.9",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "contract-retriever=contract_retriever.cli:main",
        ],
    },
)
