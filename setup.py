from setuptools import find_packages, setup

setup(
    name="PyAdio",
    version="0.1.0",
    packages=find_packages(),
    install_requires=["pyserial>=3.5", "pydantic>=2.10.4"],
    entry_points={
        "console_scripts": [],
    },
    author="Takumi Nishimura",
    author_email="clp13218@nitech.jp",
    description="Python library for ADio",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/takumi-nishimura/PyAdio",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.9",
    project_urls={"source": "https://github.com/takumi-nishimura/PyAdio.git"},
)
