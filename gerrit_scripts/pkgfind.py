#!/usr/bin/env python3

import argparse
import json
import logging
import sys
import urllib.parse

import requests

GERRIT_BASE = 'https://gerrit.mcp.mirantis.net'
GERRIT_CHANGE = '{base_url}/changes/{change}/?o=CURRENT_REVISION'
CHANGELOG_URL = ('{base_url}/gitweb?p=packaging/specs/{project}.git;'
                 'a=blob_plain;f=xenial/debian/changelog;'
                 'hb=refs/heads/{branch}')

LOG = logging.getLogger('pkgfind')

# TODO(pas-ha) use more common code from gerrit_api


def get_change(gerrit_url, change_id):
    url = GERRIT_CHANGE.format(base_url=gerrit_url,
                               change=urllib.parse.quote(change_id, safe=''))
    LOG.debug('querying gerrit as {}'.format(url))
    change = requests.get(url)
    if change.status_code < 400:
        return json.loads(change.text[4:])


def parse_changelog(project, branch, short_sha):
    url = CHANGELOG_URL.format(base_url=GERRIT_BASE,
                               branch=urllib.parse.quote(branch, safe=''),
                               project=urllib.parse.quote(project, safe=''))
    LOG.debug('querying git as {}'.format(url))
    changelog = requests.get(url).text.splitlines()
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
                     'version that contains this commit')
    )
    parser.add_argument(
        'change',
        help=('Gerrit change-id on gerrit: '
              'full id (<project>~<branch>~<Change-Id>), or'
              '<Change-Id> if it uniquely identifies change, or '
              'legacy numeric change id (like http(s)://<gerrit-url>/c/NNNN).')
    )
    parser.add_argument('--gerrit',
                        default=GERRIT_BASE,
                        help='Base Gerrit URL')
    args = parser.parse_args()
    return args


def main():
    logging.basicConfig(
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    LOG.setLevel(logging.INFO)
    args = parse_args()
    change = get_change(args.gerrit, args.change)
    if not change:
        LOG.error('Change {} is not found'.format(args.change))
        sys.exit(1)
    project = change['project'].split('/')[-1]
    branch = change['branch']
    short_sha = change['current_revision'][:7]
    pkg_version = parse_changelog(project, branch, short_sha)
    if pkg_version:
        print(project, pkg_version, sep=' ')
    else:
        LOG.error('Not Found')
        sys.exit(1)
