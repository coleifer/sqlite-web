import os

from setuptools import find_packages, setup

cur_dir = os.path.dirname(__file__)
readme = os.path.join(cur_dir, 'README.md')
if os.path.exists(readme):
    with open(readme) as fh:
        long_description = fh.read()
else:
    long_description = ''

setup(
    name='sqlite-browser',
    version='0.1.0',
    description='Web-based SQLite database browser.',
    long_description=long_description,
    author='Charles Leifer',
    author_email='coleifer@gmail.com',
    url='https://github.com/coleifer/sqlite-browser',
    license='MIT',
    install_requires=[
    ],
    include_package_data=True,
    packages=find_packages(),
    package_data={
        'sqlite_browser': [
            'static/*/*',
            'templates/*'
        ],
    },
    entry_points={
        'console_scripts': [
            'sqlite_browser = sqlite_browser.sqlite_browser:main'
        ],
    },
    classifiers=[
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
    ],
    zip_safe=False,
)
