from __future__ import absolute_import

import yaml
import logging

import os
import subprocess

import dnf
import dnf.cli
import dnf.exceptions
import dnf.subject

from rpm_patcher.arg_parser import ArgumentParser
from rpm_patcher.patches import PatchSetDict
from rpm_patcher.builder import PackageBuilder
from rpm_patcher.which import which
from rpm_patcher.util import ensure_dir, flatten

logger = logging.getLogger('dnf.plugin')


class RPMPatcherPlugin(dnf.Plugin):
    """RPM-Patcher DNF plugin"""

    name = 'rpm-patcher'

    def __init__(self, base, cli):
        super(RPMPatcherPlugin, self).__init__(base, cli)

        if cli:
            cli.register_command(RPMPatcherCommand)

_aliases = ('rpm-patcher',)


def arg_parser():
    parser = ArgumentParser(_aliases[0])
    arg = parser.add_argument

    arg('package',
        help='Package name')
    arg('config_file',
        help='Configuration file (YAML format)')
    arg('-a', '--arch', default=None,
        help='Manual architecture override')
    arg('-s', '--source-only',
        action='store_true',
        help='Only build source packages (omit binaries)')
    arg('-r', '--build-root',
        default='~/rpmbuilda',
        help='Select a root directory for downloads and build')
    arg('-d', '--build-deps', default=False,
        action='store_true',
        help='Automatically install build dependencies')
    arg('-p', '--enable-patch', dest='enabled_patches',
        action='append',
        help='Enables a patch from the configuration. Supports wildcards.')
    arg('-P', '--disable-patch', dest='disabled_patches',
        action='append',
        help='Disables a patch from the configuration. Supports wildcards.')
    arg('-q', '--quiet', action='store_true',
        help="Silence rpmbuild output")

    return parser


class RPMPatcherCommand(dnf.cli.Command):
    aliases = ("rpm-patcher",)
    summary = "Build a source RPM applying custom sets of patches"

    _parser = arg_parser()
    usage = _parser.format_help()

    def __init__(self, *args, **kwargs):
        super(RPMPatcherCommand, self).__init__(*args, **kwargs)

        self.opts = None
        self.download_command = None
        self.builddep_command = None
        self.dnf_args = None

    def check_prerequisites(self):
        bins = ('rpm2cpio', 'cpio', 'rpmbuild', 'mock')
        missing = filter(lambda b: not which(b), bins)

        if missing:
            raise dnf.exceptions.Error(
                "Missing needed binaries '{0}' in PATH".format(
                    ', '.join(missing)))

        download_command = self.cli.cli_commands.get('download')
        if not download_command:
            raise dnf.exceptions.Error("Missing 'download' plugin")

        builddep_command = self.cli.cli_commands.get('builddep')
        if not builddep_command:
            raise dnf.exceptions.Error("Missing 'builddep' plugin")

    @classmethod
    def process_config_file(cls, path):
        base_path = os.path.realpath(os.path.dirname(path))

        with open(path, 'r') as fp:
            data = yaml.load(fp)
            return PatchSetDict.from_dict(data['patches']), base_path

    @classmethod
    def setup_build_root(cls, build_root):
        build_root = os.path.expanduser(build_root)
        try:
            ensure_dir(build_root)
        except OSError as e:
            raise dnf.exceptions.Error(
                "Failed to create build root: " + str(e))

    def configure(self, args):
        demands = self.cli.demands

        demands.available_repos = True
        demands.resolving = True
        demands.sack_activation = True

        self.opts = self._parser.parse_args(args)
        if self.opts.build_deps:
            demands.root_user = True

        self.dnf_args = self.base.args[:-len(args) - 1]

    def _run_dnf_command(self, command, args, *call_args, **call_kwargs):
        cmd = [dnf.const.PROGRAM_NAME] + self.dnf_args + [command] + args
        logger.debug("Running " + str(cmd))
        return subprocess.check_call(cmd, *call_args, **call_kwargs)

    def run(self, args):
        if self.opts.help_cmd:
            self._parser.print_help()
            return

        self.check_prerequisites()

        build_root = os.path.expanduser(self.opts.build_root) \
            if self.opts.build_root else None

        package_name = self.opts.package
        if not package_name.endswith(".rpm"):
            subject = dnf.subject.Subject(package_name)
            query = subject.get_best_query(self.base.sack)

            try:
                installed_package = next(iter(query.installed()))
            except StopIteration:
                installed_package = None

            print('Installed package version: ' + str(installed_package))

            try:
                packages = list(query.available().latest())
                packages_with_src = []
                for package in packages:
                    if package.sourcerpm:
                        logger.info("Found package: " + str(package))
                        packages_with_src.append(package)
                    else:
                        logger.info("Found package without source:" + str(package))

                package = packages_with_src[0]
            except IndexError:
                package = None

            if not package:
                print('Package not found.')
                return 1

            print('Found package: ' + str(package))

            source_rpm_path = os.path.join(os.getcwd(), package.sourcerpm)

            try:
                self._run_dnf_command('download', [
                    '--source', '--destdir', os.getcwd(),
                    package.sourcerpm[:-len(".src.rpm")]
                ])
            except subprocess.CalledProcessError:
                raise dnf.exceptions.Error("download command failed")

            if not os.path.isfile(source_rpm_path):
                fmt = "Source RPM file '{0}' is missing (please report this bug!)"
                raise dnf.exceptions.Error(fmt.format(source_rpm_path))
        else:
            source_rpm_path = package_name

        logger.debug("build root: " + build_root)

        self.setup_build_root(self.opts.build_root)

        patches, base_path = self.process_config_file(self.opts.config_file)

        if self.opts.enabled_patches:
            patches.filter(self.opts.enabled_patches)

        if self.opts.disabled_patches:
            patches.filter(self.opts.disabled_patches, invert=True)

        if not patches:
            raise dnf.exceptions.Error(
                "No patches found or selected, nothing to do.")

        logger.info("Enabled patch sets: {0}".format(', '.join(patches.keys())))

        patch_list = flatten(patches.values())
        for patch in patch_list:
            logger.info("Enabled patch: {0}".format(patch.file))

        if self.opts.build_deps:
            try:
                self._run_dnf_command('builddep', [source_rpm_path])
            except subprocess.CalledProcessError:
                raise dnf.exceptions.Error("builddep command failed")

        builder = PackageBuilder(
            package_file=source_rpm_path,
            build_root=build_root,
            patches=patch_list,
            base_path=base_path,
            source_only=self.opts.source_only,
            arch=self.opts.arch,
            quiet=self.opts.quiet)

        #try:
        builder.build()
        #except Exception as e:
        #    raise dnf.exceptions.Error("Build failed: " + str(e))
