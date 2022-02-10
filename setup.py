# coding: utf-8

import sys

from setuptools import find_packages, setup

from paradox import VERSION

needs_pytest = {"pytest", "test", "ptr"}.intersection(sys.argv)
pytest_runner = ["pytest-runner"] if needs_pytest else []

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name="paradox-alarm-interface",
    version=VERSION,
    author="João Paulo Barraca",
    author_email="jpbarraca@gmail.com",
    description="Interface to Paradox Alarm Panels",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/ParadoxAlarmInterface/pai",
    download_url=f"https://github.com/ParadoxAlarmInterface/pai/archive/{VERSION}.tar.gz",
    packages=find_packages(exclude=["tests", "tests.*", "config.*", "docs.*"]),
    install_requires=["construct~=2.9.43", "argparse>=1.4.0", "python-slugify>=4.0.1"],
    python_requires=">=3.7",
    setup_requires=["wheel"] + pytest_runner,
    tests_require=[
        "pytest",
        "pytest-asyncio>=0.17",
        "pytest-env",
        "pytest-mock",
        "mock"
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Eclipse Public License 2.0 (EPL-2.0)",
        "Operating System :: OS Independent",
    ],
    extras_require={
        "YAML": ["pyyaml>=5.2.0"],
        "Serial": ["pyserial-asyncio>=0.4"],
        "IP": ["requests>=2.20.0"],
        "MQTT": ["paho_mqtt>=1.5.0"],
        "Pushbullet": ["pushbullet.py>=0.11.0", "ws4py>=0.4.2"],
        "Pushover": ["chump>=1.6.0"],
        "Signal": ["pygobject>=3.20.0", "pydbus>=0.6.0", "gi>=1.2"],
    },
    entry_points={
        "console_scripts": [
            "ip150-connection-decrypt = paradox.console_scripts.ip150_connection_decrypt:main [YAML]",
            "pai-service = paradox.console_scripts.pai_run:main",
            "pai-dump-memory = paradox.console_scripts.pai_dump_memory:main",
        ]
    },
    license="EPL",
)
