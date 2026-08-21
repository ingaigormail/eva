from setuptools import setup, find_packages

setup(
    name="avcars",
    version="0.1.0",
    packages=find_packages(include=["avcars*"]),
    install_requires=[
        "PyYAML>=6.0",
        "pydantic>=2.0",
    ],
    python_requires=">=3.10",
)
