#!/usr/bin/python2.7
# -*- coding: utf-8 -*-
"""
Mirror Univention repository server.
"""
# Copyright 2009-2018 Univention GmbH
#
# http://www.univention.de/
#
# All rights reserved.
#
# The source code of this program is made available
# under the terms of the GNU Affero General Public License version 3
# (GNU AGPL V3) as published by the Free Software Foundation.
#
# Binary versions of this program provided by Univention to you as
# well as other copyrighted, protected or trademarked materials like
# Logos, graphics, fonts, specific documentations and configurations,
# cryptographic keys etc. are subject to a license agreement between
# you and Univention and not subject to the GNU AGPL V3.
#
# In the case you use this program under the terms of the GNU AGPL V3,
# the program is provided in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License with the Debian GNU/Linux or Univention distribution in file
# /usr/share/common-licenses/AGPL-3; if not, see
# <http://www.gnu.org/licenses/>.

import os
import errno
import re
import subprocess
import itertools
import logging
from operator import itemgetter
from debian.deb822 import Packages
from apt import apt_pkg

from tools import UniventionUpdater, NullHandler
from ucs_version import UCS_Version
from repo_url import UcsRepoUrl
try:
    import univention.debug as ud
except ImportError:
    import univention.debug2 as ud


def makedirs(dirname, mode=0o755):
    """
    Recursively create directory hierarchy will all parent directories.

    :param str dirname: Name of the directory to create.
    :param int mode: Directory permissions.
    """
    try:
        os.makedirs(dirname, mode)
    except OSError as ex:
        if ex.errno != errno.EEXIST:
            raise


class UniventionMirror(UniventionUpdater):

    def __init__(self, check_access=True):
        """
        Create new mirror with settings from UCR.

        :param bool check_access: Check if repository server is reachable on init.
        :raises ConfigurationError: if configured server is not available immediately.
        """
        UniventionUpdater.__init__(self, check_access)
        self.log = logging.getLogger('updater.Mirror')
        self.log.addHandler(NullHandler())
        self.repository_path = self.configRegistry.get('repository/mirror/basepath', '/var/lib/univention-repository')

        version_end = self.configRegistry.get('repository/mirror/version/end') or self.current_version
        self.version_end = UCS_Version(version_end)
        version_start = self.configRegistry.get('repository/mirror/version/start') or (self.version_major, 0, 0)
        self.version_start = UCS_Version(version_start)
        # set architectures to mirror
        archs = self.configRegistry.get('repository/mirror/architectures', '')
        if archs:
            self.architectures = archs.split(' ')

    def config_repository(self):
        """
        Retrieve configuration to access repository. Overrides :py:class:`univention.updater.UniventionUpdater`.
        """
        self.online_repository = self.configRegistry.is_true('repository/mirror', True)
        self.repourl = UcsRepoUrl(self.configRegistry, 'repository/mirror')
        self.sources = self.configRegistry.is_true('repository/mirror/sources', False)
        self.timeout = float(self.configRegistry.get('repository/mirror/timeout', 30))
        self.http_method = self.configRegistry.get('repository/mirror/httpmethod', 'HEAD').upper()
        self.script_verify = self.configRegistry.is_true('repository/mirror/verify', True)

    def release_update_available(self, ucs_version=None, errorsto='stderr'):
        """
        Check if an update is available for the `ucs_version`.

        :param str ucs_version: The UCS release to check.
        :param str errorsto: Select method of reporting errors; on of 'stderr', 'exception', 'none'.
        :returns: The next UCS release or None.
        :rtype: str or None
        """
        if not ucs_version:
            ucs_version = self.current_version
        return self.get_next_version(UCS_Version(ucs_version), [], errorsto)

    def mirror_repositories(self):
        """
        Uses :command:`apt-mirror` to copy a repository.
        """
        # check if the repository directory structure exists, otherwise create it
        makedirs(self.repository_path)

        # these sub-directories are required by apt-mirror
        for dirname in ('skel', 'mirror', 'var'):
            path = os.path.join(self.repository_path, dirname)
            makedirs(path)
        path = os.path.join(self.repository_path, 'mirror', 'univention-repository')
        try:
            os.symlink('.', path)
        except OSError as ex:
            if ex.errno != errno.EEXIST:
                raise

        log = open('/var/log/univention/repository.log', 'a')
        try:
            return subprocess.call('/usr/bin/apt-mirror', stdout=log, stderr=log, shell=False)
        finally:
            log.close()

    def mirror_update_scripts(self):
        """
        Mirrors the :file:`preup.sh` and :file:`postup.sh` scripts.
        """
        start = self.version_start
        end = self.version_end
        parts = self.parts
        archs = ('all',)

        repos = self._iterate_version_repositories(start, end, parts, archs)  # returns generator

        components = self.get_components(only_localmirror_enabled=True)
        comp = self._iterate_component_repositories(components, start, end, archs, for_mirror_list=True)  # returns generator

        all_repos = itertools.chain(repos, comp)  # concatenate all generators into a single one
        for server, struct, phase, path, script in UniventionUpdater.get_sh_files(all_repos, self.script_verify):
            self.log.info('Mirroring %s:%r/%s to %s', server, struct, phase, path)
            assert script is not None, 'No script'

            # use prefix if defined - otherwise file will be stored in wrong directory
            if server.prefix:
                filename = os.path.join(self.repository_path, 'mirror', server.prefix, path)
            else:
                filename = os.path.join(self.repository_path, 'mirror', path)

            # Check disabled, otherwise files won't get refetched if they change on upstream server
            # if os.path.exists(filename):
            #   ud.debug(ud.NETWORK, ud.ALL, "Script already exists, skipping: %s" % filename)
            #   continue

            makedirs(os.path.dirname(filename))
            fd = open(filename, "w")
            try:
                fd.write(script)
                ud.debug(ud.ADMIN, ud.INFO, "Successfully mirrored: %s" % filename)
            finally:
                fd.close()

    def list_local_repositories(self, start=None, end=None, maintained=True, unmaintained=False):
        """
        This function returns a sorted list of local (un)maintained repositories.

        :param start: smallest version that shall be returned.
        :type start: UCS_Version or None
        :param end: largest version that shall be returned.
        :type end: UCS_Version or None
        :param bool maintained: True if list shall contain maintained repositories.
        :param bool unmaintained: True if list shall contain unmaintained repositories.
        :returns: A sorted list of repositories as (directory, UCS_Version, is_maintained) tuples.
        :rtype: list[tuple(str, UCS_Version, bool)]
        """
        result = []
        repobase = os.path.join(self.repository_path, 'mirror')
        RErepo = re.compile('^%s/(\d+[.]\d)/(maintained|unmaintained)/(\d+[.]\d+-\d+)$' % (re.escape(repobase),))
        for dirname, subdirs, files in os.walk(repobase):
            match = RErepo.match(dirname)
            if match:
                if not maintained and match.group(2) == 'maintained':
                    continue
                if not unmaintained and match.group(2) == 'unmaintained':
                    continue

                version = UCS_Version(match.group(3))
                if start is not None and version < start:
                    continue
                if end is not None and end < version:
                    continue

                result.append((dirname, version, match.group(2) == 'maintained'))

        result.sort(key=itemgetter(1))

        return result

    def update_dists_files(self):
        """
        Rewrite from
        | /var/lib/univention-repository/mirror/
        |  4.0/
        |   maintained/ >>>
        |    4.0-1/     <<<
        |     amd64/
        |      Packages (relative to <<<)
        |      *.deb
        to
        |     dists/
        |      ucs401/
        |       main/
        |        binary-amd64/
        |         Packages (relative to >>>)
        |         Release
        |        debian-installer/
        |         binary-amd64/
        |          Packages (relative to >>>)
        |       Release

        >> from sys import stderr
        >> logging.basicConfig(stream=stderr, level=logging.DEBUG)
        >> m = UniventionMirror(False)
        >> m.update_dists_files()
        """
        # iterate over all local repositories
        repos = self.list_local_repositories(start=self.version_start, end=self.version_end, unmaintained=False)
        for outdir, version, is_maintained in repos:
            self.log.info('Processing %s...', version)
            start_version = UCS_Version((version.major, 0, 0))

            dist = 'univention' if version.major < 4 else 'ucs%(major)d%(minor)d%(patchlevel)d' % version

            archs = []
            for arch in self.architectures:
                prev = [
                    (dir2, os.path.join(dir2, arch2, 'Packages'))
                    for (dir2, ver2, maint2) in repos
                    for arch2 in (arch, 'all')
                    if (
                        start_version <= ver2 <= version and
                        os.path.exists(os.path.join(dir2, arch2, 'Packages'))
                    )
                ]
                if not prev:
                    self.log.warn('No file "Packages" found for %s', arch)
                    continue
                prev.reverse()
                archs.append(arch)

                main_name = os.path.join(outdir, 'dists', dist, 'main', 'binary-%s' % arch, 'Packages')
                inst_name = os.path.join(outdir, 'dists', dist, 'main', 'debian-installer', 'binary-%s' % arch, 'Packages')
                self.log.debug('Generating %s and %s ...', main_name, inst_name)
                makedirs(os.path.dirname(main_name))
                makedirs(os.path.dirname(inst_name))
                main = open(main_name + '.tmp', 'w')
                inst = open(inst_name + '.tmp', 'w')
                try:
                    for dir2, src_name in prev:
                        self.log.debug('Appending %s ...', src_name)
                        indir = os.path.dirname(dir2)
                        with open(src_name, 'r') as src:
                            for pkg in Packages.iter_paragraphs(src):
                                abs_deb = os.path.join(indir, pkg['Filename'])
                                pkg['Filename'] = os.path.relpath(abs_deb, outdir)
                                dst = inst if pkg['Section'] == 'debian-installer' else main
                                pkg.dump(dst)
                                dst.write('\n')
                finally:
                    main.close()
                    inst.close()

                self._compress(main_name)
                self._compress(inst_name)

                rel_name = os.path.join(outdir, 'dists', dist, 'main', 'binary-%s' % arch, 'Release')
                self.log.debug('Generating %s ...', rel_name)
                with open(rel_name, 'w') as rel:
                    print >> rel, 'Archive: stable'
                    print >> rel, 'Origin: Univention'
                    print >> rel, 'Label: Univention'
                    print >> rel, 'Version: %(major)d.%(minor)d.%(patchlevel)d' % version
                    print >> rel, 'Component: main'
                    print >> rel, 'Architecture: %s' % (arch,)

            if archs:
                self._release(outdir, dist, archs, version)

    def _compress(self, filename):
        """
        Compress given file.

        :param str filename: The name of the file to compress.
        """
        self.log.debug('Compressing %s ...', filename)
        sorter = subprocess.Popen(
            ('apt-sortpkgs', filename + '.tmp'),
            stdout=subprocess.PIPE,
        )
        tee = subprocess.Popen(
            ('tee', filename),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        gzip = subprocess.Popen(
            ('gzip',),
            stdin=tee.stdout,
            stdout=open(filename + '.gz', 'wb'),
        )
        tee.stdout.close()
        prev = None
        for pkg in Packages.iter_paragraphs(sorter.stdout):
            if prev:
                if prev["Package"] != pkg["Package"]:
                    tee.stdin.write("%s\n" % prev)
                elif prev["Filename"].startswith('../') and not pkg["Filename"].startswith('../'):
                    pass
                elif not prev["Filename"].startswith('../') and pkg["Filename"].startswith('../'):
                    continue
                elif apt_pkg.version_compare(prev["Version"], pkg["Version"]) >= 0:
                    continue
            prev = pkg
        if prev:
            tee.stdin.write("%s\n" % prev)
        tee.stdin.close()
        rc_sorter, rc_tee, rc_gzip = sorter.wait(), tee.wait(), gzip.wait()
        self.log.debug('sorter=%d tee=%d gzip=%d', rc_sorter, rc_tee, rc_gzip)
        os.remove(filename + '.tmp')

    def _release(self, outdir, dist, archs, version):
        """
        Generate a new :file:`Release` file.

        :param str outdir: The name of the output directory.
        :param str dist: The name of the distribution.
        :param archs: The list of architectures.
        :type archs: list(str)
        :param UCS_Version version: The UCS release version.
        """
        rel_name = os.path.join(outdir, 'dists', dist, 'Release')
        self.log.info('Generating %s ...', rel_name)
        cmd = (
            'apt-ftparchive',
            '-o', 'APT::FTPArchive::Release::Origin=Univention',
            '-o', 'APT::FTPArchive::Release::Label=Univention',
            '-o', 'APT::FTPArchive::Release::Suite=stable',
            '-o', 'APT::FTPArchive::Release::Version=%(major)d.%(minor)d.%(patchlevel)d' % version,
            '-o', 'APT::FTPArchive::Release::Codename=%s' % (dist,),
            '-o', 'APT::FTPArchive::Release::Architectures=%s' % (' '.join(archs),),
            '-o', 'APT::FTPArchive::Release::Components=main',
            'release',
            os.path.join('dists', dist),
        )
        self.log.debug('%r @ %s', cmd, outdir)
        try:
            os.remove(rel_name)
        except OSError as ex:
            if ex.errno != errno.ENOENT:
                raise
        tmp_name = rel_name + '.tmp'
        subprocess.call(cmd, stdout=open(tmp_name, 'wb'), cwd=outdir)
        os.rename(tmp_name, rel_name)

    def run(self):
        """
        starts the mirror process.
        """
        self.mirror_repositories()
        self.mirror_update_scripts()
        self.update_dists_files()


if __name__ == '__main__':
    import doctest
    from sys import exit
    exit(doctest.testmod()[0])
