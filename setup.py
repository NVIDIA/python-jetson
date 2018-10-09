#!/usr/bin/python3

import setuptools

with open('README.md', 'r') as file:
    long_description = file.read()

setuptools.setup(
    name = 'python-jetson',
    version = '0.0.0',
    author = 'Thierry Reding',
    author_email = 'treding@nvidia.com',
    description = 'NVIDIA Jetson utilities',
    long_description = long_description,
    long_description_content_type = 'text/markdown',
    url = 'https://githum.com/NVIDIA/python-jetson',
    packages = setuptools.find_packages(),
    classifiers = [
        'Programming Language :: Python :: 3',
        'License :: OSI Approvied :: MIT License',
        'Operating System :: OS Independent',
    ],
    scripts = [
        'bin/jetson-control',
        'bin/jetson-demux',
    ],
    package_dir = { '': '.' },
    package_data = {
        'jetson': [ ],
    }
)
