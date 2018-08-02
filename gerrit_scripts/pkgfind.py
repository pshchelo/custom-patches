#!/usr/bin/env python3

import argparse
import json
import logging
import sys

import requests

GERRIT_BASE = 'https://gerrit.mcp.mirantis.net'
GERRIT_CHANGE = '{base_url}/changes/?o=CURRENT_REVISION&q=change:{change}'
CHANGELOG_URL = ('{base_url}/gitweb?p=packaging/specs/{project}.git;'
                 'a=blob_plain;f=xenial/debian/changelog;'
                 'hb=refs/heads/{branch}')

LOG = logging.getLogger('pkgfind')

def get_change(change_id):
    change = requests.get(GERRIT_CHANGE.format(base_url=GERRIT_BASE,
                                               change=change_id))
    if change.status_code < 400:
        return json.loads(change.text[4:])[0]


def parse_changelog(project, branch, short_sha):
    changelog = requests.get(
        CHANGELOG_URL.format(base_url=GERRIT_BASE,
                             branch=branch, project=project)
    ).text.splitlines()
    earliest = None
    for line in changelog:
        if line.startswith(project):
            current_pkg = line
            continue
        if '* ' + short_sha in line:
            earliest = current_pkg
    if earliest:
        return earliest.split()[1].strip('()')

def parse_args():
    parser = argparse.ArgumentParser(
        description=('Using Geriit Change-Id, find the oldest package version '
                     'that contains this commit')
    )
    parser.add_argument(
        'change',
        help=('Change id on gerrit.')
    )
    args = parser.parse_args()
    return args


def main():
    logging.basicConfig(
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    LOG.setLevel(logging.INFO)
    args = parse_args()
    change_id = args.change
    change = get_change(change_id)
    project = change['project'].split('/')[-1]
    branch = change['branch']
    short_sha = change['current_revision'][:7]
    pkg_version = parse_changelog(project, branch, short_sha)
    if pkg_version:
        print(project, pkg_version, sep=' ')
    else:
        print('Not Found')
