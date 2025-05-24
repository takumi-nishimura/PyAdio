from setuptools import find_packages, setup

setup(
    name="PyAdio",
    version="0.2.0", # Version updated to reflect new features/changes
    packages=find_packages(where="src"), # Specify 'src' directory
    package_dir={"": "src"}, # Specify 'src' directory
    install_requires=[
        "pyserial>=3.5", 
        "pydantic>=2.10.4",
        "pyserial-asyncio>=0.6" # Added pyserial-asyncio
    ],
    entry_points={
        "console_scripts": [],
    },
    author="Takumi Nishimura",
    author_email="clp13218@nitech.jp",
    description="Python library for ADio with asynchronous I/O support.", # Updated description
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/takumi-nishimura/PyAdio",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.9", # pyserial-asyncio might require newer Python versions too
    project_urls={"source": "https://github.com/takumi-nishimura/PyAdio.git"},
)
