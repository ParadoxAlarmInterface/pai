import sys
import setuptools

from setuptools.command.test import test as TestCommand

class PyTest(TestCommand):
    user_options = [("pytest-args=", "a", "Arguments to pass to pytest")]

    def initialize_options(self):
        TestCommand.initialize_options(self)
        self.pytest_args = ""

    def run_tests(self):
        import shlex

        # import here, cause outside the eggs aren't loaded
        import pytest

        errno = pytest.main(shlex.split(self.pytest_args))
        sys.exit(errno)

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
    tests_require=[
        'pytest',
        'pytest-mock',
        'mock'
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: EPL License",
        "Operating System :: OS Independent",
    ],
    cmdclass={"pytest": PyTest},
)