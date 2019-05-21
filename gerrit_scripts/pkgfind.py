#!/usr/bin/env python3

import argparse
import logging
import os
import sys
import urllib.parse

import requests
from pygerrit2 import rest

GERRIT_BASE = 'https://gerrit.mcp.mirantis.com'
GERRIT_CHANGE = '/changes/{change}/?o=CURRENT_REVISION'
CHANGELOG_URL = ('{base_url}/gitweb?p=packaging/specs/{project}.git;'
                 'a=blob_plain;f={changelog};hb=refs/heads/{branch}')
SPEC_CHANGELOG = 'xenial/debian/changelog'
DISTROS = ('xenial', 'bionic')

LOG = logging.getLogger('pkgfind')


def mask_password(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.password is None:
        return url
    return urllib.parse.urlunsplit((
        parsed.scheme,
        parsed.netloc.replace(parsed.password, "***"),
        parsed.path,
        parsed.query,
        parsed.fragment))


def gerrit_access(gerrit_base_url, user, password, auth_mode):
    auth = None
    gerrit_url = gerrit_base_url
    if user and password:
        if auth_mode == 'digest':
            auth_cls = rest.auth.HTTPDigestAuth
        else:
            auth_cls = rest.auth.HTTPBasicAuth
        auth = auth_cls(user, password)
        gerrit_url += '/a'
    return gerrit_url, auth


def get_change(gerrit_url, change_id, auth=None):
    gerrit = rest.GerritRestAPI(gerrit_url, auth=auth)
    query = GERRIT_CHANGE.format(change=urllib.parse.quote(change_id, safe=''))
    LOG.debug('querying gerrit as {}'.format(query))
    change, r = gerrit.get(query, return_response=True)
    if r.status_code < 400:
        return change


def parse_changelog(gerrit, project, branch, short_sha, auth=None):
    spec_changelog = SPEC_CHANGELOG
    br_parts = set(branch.split('/'))
    for d in DISTROS:
        if d in br_parts:
            spec_changelog = spec_changelog.replace(d+'/', '')
            break

    url = CHANGELOG_URL.format(base_url=gerrit,
                               branch=urllib.parse.quote(branch, safe=''),
                               changelog=urllib.parse.quote(spec_changelog,
                                                            safe=''),
                               project=urllib.parse.quote(project, safe=''))
    LOG.debug('querying git as {}'.format(mask_password(url)))
    changelog = requests.get(url, auth=auth).text.splitlines()
    earliest = None
    current_pkg = None
    for line in changelog:
        if line.startswith(project) or line.startswith('python-'+project):
            current_pkg = line
            continue
        if '* ' + short_sha in line:
            earliest = current_pkg
    if earliest:
        return earliest.split()[1].strip('()')


def parse_args():
    parser = argparse.ArgumentParser(
        description=('Using Geriit change-id, find the oldest package '
                     'version that contains this commit in MCP Gerrit')
    )
    parser.add_argument(
        'change',
        help=('Gerrit change-id on gerrit: '
              'full id (<project>~<branch>~<Change-Id>), or'
              '<Change-Id> if it uniquely identifies change, or '
              'legacy numeric change id (like http(s)://<gerrit-url>/c/NNNN).')
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    parser.add_argument(
        '--gerrit',
        default=GERRIT_BASE,
        help='Base Gerrit URL'
    )
    parser.add_argument(
        '--gerrit-username',
        default=os.getenv('CUSTOM_PATCHES_GERRIT_USERNAME'),
        help=('Gerrit HTTP user name to access Gerrit HTTP API/repos. '
              'Defaults to CUSTOM_PATCHES_GERRIT_USERNAME shell var')
    )
    parser.add_argument(
        '--gerrit-password',
        default=os.getenv('CUSTOM_PATCHES_GERRIT_HTTP_PASSWORD'),
        help=('Gerrit HTTP password. '
              'Defaults to CUSTOM_PATCHES_GERRIT_HTTP_PASSWORD shell var.')
    )
    parser.add_argument(
        '--gerrit-auth-mode',
        default='basic',
        choices=['basic', 'digest'],
        help=("Auth mode the Gerrit uses.")
    )
    args = parser.parse_args()
    return args


def main():
    logging.basicConfig(
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    args = parse_args()
    if args.debug:
        LOG.setLevel(logging.DEBUG)
    else:
        LOG.setLevel(logging.WARNING)
    gerrit_url, auth = gerrit_access(args.gerrit,
                                     args.gerrit_username,
                                     args.gerrit_password,
                                     args.gerrit_auth_mode)
    change = get_change(gerrit_url, args.change, auth)
    if not change:
        LOG.error('Change {} is not found'.format(args.change))
        return 1
    project = change['project'].split('/')[-1]
    branch = change['branch']
    short_sha = change['current_revision'][:7]
    pkg_version = parse_changelog(gerrit_url, project, branch, short_sha, auth)
    if pkg_version:
        print(project, pkg_version, sep=' ')
    else:
        LOG.error('Commit Not Found in package changelog')
        return 1


if __name__ == '__main__':
    sys.exit(main())
