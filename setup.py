import os
from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))

with open(os.path.join(here, 'README.rst')) as f:
    README = f.read()

requires = [
    'setuptools',
    'CouchDB',
    'jsonpatch',
    'pytz',
    'gevent',
]
test_requires = requires + [
    'webtest',
    'python-coveralls',
    'openprocurement.api',
    'nose',
]

entry_points = {
    'console_scripts': [
        'concord = openprocurement.concord.daemon:main'
    ]
}

setup(name='openprocurement.concord',
      version='0.7dp',
      description="Conflict resolution daemon",
      long_description=README,
      classifiers=[
          "License :: OSI Approved :: Apache Software License",
          "Programming Language :: Python",
      ],
      keywords="couchdb conflict resolution daemon",
      author='Quintagroup, Ltd.',
      author_email='info@quintagroup.com',
      license='Apache License 2.0',
      url='https://github.com/openprocurement/openprocurement.concord',
      packages=find_packages(exclude=['ez_setup']),
      namespace_packages=['openprocurement'],
      include_package_data=True,
      zip_safe=False,
      install_requires=requires,
      tests_require=test_requires,
      extras_require={'test': test_requires},
      test_suite="openprocurement.concord.tests.main.suite",
      entry_points=entry_points)
