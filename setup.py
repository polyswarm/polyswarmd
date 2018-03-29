import os
from setuptools import setup
from glob import iglob

def listdir(d):
    return [g for g in iglob(os.path.join(d, '**', '*'), recursive=True) if os.path.isfile(g)]

setup(name='polyswarmd',
      version='0.1',
      description='Daemon for interacting with the PolySwarm marketplace',
      author = 'PolySwarm Developers',
      author_email = 'info@polyswarm.io',
      url='https://github.com/polyswarm/polyswarmd',
      entry_points = {
          'gui_scripts': ['polyswarmd=polyswarmd:main'],
      },
      data_files=[
          ('frontend', listdir(os.path.join('frontend', 'build'))),
          ('truffle', listdir(os.path.join('truffle', 'build'))),
      ]
)
