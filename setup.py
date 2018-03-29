from setuptools import setup

def parse_requirements():
    with open('requirements.txt', 'r') as f:
        return f.read().splitlines()

setup(name='polyswarmd',
      version='0.1',
      description='Daemon for interacting with the PolySwarm marketplace',
      author = 'PolySwarm Developers',
      author_email = 'info@polyswarm.io',
      url='https://github.com/polyswarm/polyswarmd',
      install_requires=parse_requirements(),
      packages=['polyswarmd'],
      package_dir={
          'polyswarmd': '.',
      },
      package_data={
          'polyswarmd': ['polyswarmd.cfg', 'frontend/build/**/*', 'truffle/build/**/*'],
      },
      entry_points = {
          'console_scripts': ['polyswarmd=polyswarmd.polyswarmd:main'],
      },
)
