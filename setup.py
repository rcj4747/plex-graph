"""
Graph relationships between movies on a plex server
"""
import os

from setuptools import find_packages, setup

reqs_path = os.path.join(os.path.dirname(__file__), 'requirements.txt')

with open(reqs_path, 'r') as req_file:
    dependencies = req_file.readlines()

setup(
    name='plex_graph',
    version='0.1.0',
    license='GPLv3',
    author='Robert C Jennings',
    author_email='rcj4747@gmail.com',
    description='Graph relationships between movies on a plex server',
    long_description=__doc__,
    packages=find_packages(exclude=['tests']),
    include_package_data=True,
    zip_safe=False,
    platforms='any',
    install_requires=dependencies,
    entry_points={
        'console_scripts': [
            'plex-graph = plex_graph.cli:plex_graph',
        ],
    },
)
