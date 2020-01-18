from setuptools import find_packages, setup


def parse_requirements():
    with open('requirements.txt', 'r') as f:
        return ['{2} @ {0}'.format(*r.partition('#egg=')) if '#egg=' in r else r for r in f.read().splitlines()]


setup(name='polyswarmd',
      version='2.2.0',
      description='Daemon for interacting with the PolySwarm marketplace',
      author = 'PolySwarm Developers',
      author_email = 'info@polyswarm.io',
      url='https://github.com/polyswarm/polyswarmd',
      license='MIT',
      install_requires=parse_requirements(),
      include_package_data=True,
      packages=find_packages('src'),
      package_dir={'': 'src/'},
      entry_points={
          'console_scripts': ['polyswarmd=polyswarmd.__main__:main'],
      },
)
