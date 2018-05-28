from setuptools import setup

def parse_requirements():
    with open('requirements.txt', 'r') as f:
        return f.read().splitlines()

setup(name='polyswarmd',
      version='0.2',
      description='Daemon for interacting with the PolySwarm marketplace',
      author = 'PolySwarm Developers',
      author_email = 'info@polyswarm.io',
      url='https://github.com/polyswarm/polyswarmd',
      license='MIT',
      install_requires=parse_requirements(),
      packages=['polyswarmd'],
      package_dir={
          'polyswarmd': 'src/polyswarmd',
      },
      package_data={
          'polyswarmd': ['config/*', 'truffle/build/**/*'],
      },
      entry_points = {
          'console_scripts': ['polyswarmd=polyswarmd.__main__:main'],
      },
)
