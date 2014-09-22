#!/usr/bin/env python

from __future__ import print_function

import datetime
import re
import glob
import logging

import os
import sys
import shutil
import subprocess

try:
    import urlparse
except ImportError:
    import urllib.parse as urlparse

import urlgrabber

from .patches import Patch
from .util import ensure_dir, TeeWriter


class PackageBuilder(object):
    def __init__(self, package_file, build_root, patches, base_path, arch=None,
                 logger=logging, source_only=False, quiet=False, log_file=None):
        self.package_file = package_file
        self.patches = list(patches)
        self.base_path = base_path
        self.arch = arch
        self.logger = logger
        self.source_only = bool(source_only)
        self.quiet = quiet
        self.log_file = log_file

        ext = ".src.rpm"

        if not package_file.endswith(ext):
            raise ValueError("Invalid package file: must be a source rpm")

        # Check file existence
        open(self.package_file, 'r').close()

        self.package_name = os.path.basename(package_file)[:-len(ext)]

        self.build_root = os.path.join(build_root, self.package_name)
        ensure_dir(self.build_root)

        for subdir in ('SPECS', 'SOURCES', 'RPMS', 'SRPMS', 'BUILD'):
            ensure_dir(self.build_dir(subdir))

    def build_dir(self, name):
        return os.path.join(self.build_root, name)

    def build(self):
        self.extract_package()

        spec_file = next(glob.iglob(os.path.join(self.build_dir('SPECS'),
                                                 '*.spec')))

        patches = self.download_patches()
        self.logger.debug(patches)

        self.insert_patches(spec_file)

        import rpm
        rpm.spec
        #self.build_rpms(spec_file)

    def extract_package(self):
        p1 = subprocess.Popen(['rpm2cpio', self.package_file],
                              stdout=subprocess.PIPE)
        p2 = subprocess.Popen(['cpio', '--extract', '--make-directories',
                               '--preserve-modification-time',
                               '--no-preserve-owner', '--unconditional'],
                              cwd=self.build_dir('SOURCES'), stdin=p1.stdout)

        p2.wait()
        if p1.returncode != 0 or p2.returncode != 0:
            return False

        for spec in glob.iglob(os.path.join(self.build_dir('SOURCES'),
                                            '*.spec')):
            shutil.move(spec, self.build_dir('SPECS'))

        return True

    def _process_patch(self, patch):
        import pdb; pdb.set_trace()

        url = urlparse.urlparse(patch.file)
        src_dir = self.build_dir('SOURCES')

        if not url.scheme:
            filename = os.path.basename(url.path)
            path = os.path.join(self.base_path, filename)

            dest = os.path.join(src_dir, filename)
            if not os.path.exists(dest) or not os.path.samefile(path, dest):
                shutil.copyfile(path, dest)
        else:
            filename = url.path.rsplit('/', 1)[-1]
            dest = os.path.join(src_dir, filename)
            urlgrabber.urlgrab(url, dest)

        return Patch(filename, patch.options)

    def download_patches(self):
        return map(self._process_patch, self.patches)

    def default_log_filename(self):
        def date_str():
            now = datetime.datetime.now()
            return now.strftime('%Y-%m-%d %H:%M')

        return 'rpmbuild_{0}_{1}.log'.format(self.package_name, date_str())

    def log_filename(self):
        if not self.log_file:
            return None

        if self.log_file == '__default__':
            return self.default_log_filename()
        elif os.path.isdir(self.log_file):
            return os.path.join(self.log_file, self.default_log_filename())

        return self.log_file

    def build_rpms(self, spec_file):
        log_filename = self.log_filename()
        log_file = None

        if self.quiet:
            if log_filename:
                log_file = open(log_filename, 'w')
        elif log_filename:
            log_file = TeeWriter(os.dup(sys.stdout), open(log_filename, 'w'),
                                 close=True)

        if log_file:
            with log_file:
                return self._do_build_rpms(spec_file, log_file)
        else:
            return self._do_build_rpms(spec_file)

    def _do_build_rpms(self, spec_file, log_file=None):
        self.logger.info('Building SRPM from spec file `{0}`'.format(spec_file))

        call_args = {'stdout': log_file, 'stderr': log_file} \
            if log_file else {}

        cmd = (
            ['rpmbuild', '-D', '%_topdir {0}'.format(self.build_root)]
            + (['-bs'] if self.source_only else ['-ba'])
            + (['--quiet'] if log_file and self.quiet else [])
            + (['--target', self.arch] if self.arch else [])
            + [spec_file]
        )
        print(cmd)

        try:
            subprocess.check_call(cmd, **call_args)
        except subprocess.CalledProcessError as e:
            self.logger.error("rpmbuild failed with code {0}", e.returncode)
            return False

        return True

