# coding: utf-8

import sys
import setuptools

needs_pytest = {'pytest', 'test', 'ptr'}.intersection(sys.argv)
pytest_runner = ['pytest-runner'] if needs_pytest else []

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="paradox-alarm-interface",
    version="0.1",
    author="João Paulo Barraca",
    author_email="jpbarraca@gmail.com",
    description="Interface to Paradox Alarm Panels",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/jpbarraca/pai",
    packages=['config', 'paradox'],
    install_requires=[],
    setup_requires=[] + pytest_runner,
    tests_require=[
        'pytest',
        'pytest-env',
        'pytest-mock',
        'mock'
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: EPL License",
        "Operating System :: OS Independent",
    ]
)