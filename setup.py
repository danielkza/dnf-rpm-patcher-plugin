from distutils.core import setup

setup(
    name='rpm-patcher',
    version='0.1',
    packages=['rpm_patcher', 'dnf-plugins'],
    package_dir={'': 'src'},
    url='https://github.com/danielkza/rpm-patcher',
    license='GPLv2',
    author='danielkza',
    author_email='danielkza2@gmail.com',
    description=''
)
