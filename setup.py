# coding: utf-8

import sys
from setuptools import setup, find_packages

needs_pytest = {'pytest', 'test', 'ptr'}.intersection(sys.argv)
pytest_runner = ['pytest-runner'] if needs_pytest else []

with open('README.md', 'r') as fh:
    long_description = fh.read()

setup(
    name='paradox-alarm-interface',
    version='1.3.0',
    author='João Paulo Barraca',
    author_email='jpbarraca@gmail.com',
    description='Interface to Paradox Alarm Panels',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/ParadoxAlarmInterface/pai',
    download_url='https://github.com/ParadoxAlarmInterface/pai/archive/1.3.0.tar.gz',
    packages=find_packages(exclude=['tests', 'tests.*', 'config.*', 'docs.*']),
    install_requires=[
        'construct >= 2.9.43',
        'argparse >= 1.4.0'
    ],
    python_requires='>=3.6',
    setup_requires=[] + pytest_runner,
    tests_require=[
        'pytest',
        'pytest-asyncio',
        'pytest-env',
        'pytest-mock',
        'mock'
    ],
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: Eclipse Public License 2.0 (EPL-2.0)',
        'Operating System :: OS Independent',
    ],
    extras_require={
        'YAML':  ['PyYAML>=3.13']
    },
    entry_points={
        'console_scripts': [
            'ip150-connection-decrypt = paradox.console_scripts.ip150_connection_decrypt:main [YAML]',
            'pai-service = paradox.console_scripts.pai_run:main'
        ]
    },
    license='EPL'
)
