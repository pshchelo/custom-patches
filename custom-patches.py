#!/usr/bin/env python
# coding: utf-8

from __future__ import print_function

import argparse
import json
import logging
import os
import re

import git

LOG = logging.getLogger('custom-patches')

CHANGE_ID_PATTERN = re.compile(r'\nChange-Id:\s(?P<changeid>I[a-f0-9]{40})\n')
DEFAULT_FILTER_REGEX = (
    '^(?!(Updated from global requirements|Imported Translations from Zanata))'
)


def build_commit_dict(commits):
    commit_dict = {}
    for c in commits:
        f = CHANGE_ID_PATTERN.search(c.message)
        # filter out merge commits
        if f and len(c.parents) == 1:
            commit_dict[f.groups()[0]] = c
    return commit_dict


def prepare_repo(repo_path):
    if (os.path.exists(repo_path) and
            os.path.isdir(repo_path) and
            os.path.isdir(os.path.join(repo_path, '.git'))):
        LOG.info('Repo %s exists, updating remotes' % repo_path)
        repo = git.Repo(repo_path)
    else:
        LOG.info('Creating repo %s' % repo_path)
        os.mkdir(repo_path)
        repo = git.Repo.init(repo_path)
    return repo


def update_remotes(repo, gerrit_uri, project,
                   new_gerrit_uri=None, new_project=None):
    source_remote = 'custom_patches_source'
    target_remote = 'custom_patches_target'
    if not new_gerrit_uri:
        new_gerrit_uri = gerrit_uri
        target_remote = source_remote
    if not new_project:
        new_project = project
    gerrit_repo = os.path.join(gerrit_uri, project.strip('/'))
    if source_remote in (r.name for r in repo.remotes):
        source = repo.remotes[source_remote]
        source.set_url(gerrit_repo)
    else:
        source = repo.create_remote(source_remote, gerrit_repo)
    LOG.info("Fetching from remote %s" % gerrit_repo)
    source.update()
    if source_remote != target_remote:
        new_gerrit_repo = os.path.join(new_gerrit_uri, new_project.strip('/'))
        if target_remote in (r.name for r in repo.remotes):
            target = repo.remotes[target_remote]
            target.set_url(new_gerrit_repo)
        else:
            target = repo.create_remote(target_remote, new_gerrit_repo)
        LOG.info("Fetching from remote %s" % new_gerrit_repo)
        target.update()

    return source_remote, target_remote


def find_missing_changes(repo, source_remote, target_remote,
                         old_branch, new_branch):
    common_ancestor = repo.merge_base(
        'remotes/{remote}/{branch}'.format(remote=source_remote,
                                           branch=old_branch),
        'remotes/{remote}/{branch}'.format(remote=target_remote,
                                           branch=new_branch))[0]

    old_commits = repo.iter_commits(
        common_ancestor.hexsha+'..remotes/{remote}/{branch}'.format(
            remote=source_remote, branch=old_branch))
    new_commits = repo.iter_commits(
        common_ancestor.hexsha+'..remotes/{remote}/{branch}'.format(
            remote=target_remote, branch=new_branch))
    old_commit_dict = build_commit_dict(old_commits)
    new_commit_dict = build_commit_dict(new_commits)
    return [old_commit_dict[i]
            for i in set(old_commit_dict) - set(new_commit_dict)]


def output_commits(commits, filter_regex_str, long_out=False, json_out=None):
    filter_regex = re.compile(filter_regex_str)
    commit_dict = {}
    for c in commits:
        commit_lines = c.message.splitlines()
        title = commit_lines[0]
        message = commit_lines[1:]
        if filter_regex.match(title):
            print("{id} {title}".format(id=c.hexsha[:8],
                                        title=title))
            if long_out:
                for l in message:
                    print(" " * 9 + l)
                print("\n")
            if json_out:
                commit_dict[c.hexsha] = {'title': title, 'message': message}

    if commit_dict:
        LOG.info("Writing JSON output to %s" % json_out)
        with open(json_out, 'w') as out:
            json.dump(commit_dict, out, indent=4)


def parse_args():
    parser = argparse.ArgumentParser(
        description=('Using Geriit Change-Id, report patches in <old branch> '
                     'which are missing in the <new branch>. '
                     'Requires "GitPython" package (pip-)installed from PyPI.')
    )
    parser.add_argument(
        '--gerrit-uri',
        default=os.getenv('CUSTOM_PATCHES_GERRIT_URI'),
        help=('Gerrit URI. '
              'Defaults to CUSTOM_PATCHES_GERRIT_URI shell var')
    )
    parser.add_argument(
        '--new-gerrit-uri',
        default=os.getenv('CUSTOM_PATCHES_NEW_GERRIT_URI'),
        help=('New Gerrit repo URI. '
              'Defaults to CUSTOM_PATCHES_NEW_GERRIT_URI shell var. '
              'If empty, falls back to Gerrit URI.')
    )
    parser.add_argument(
        '--project',
        default=os.getenv('CUSTOM_PATCHES_GERRIT_PROJECT'),
        help=('Gerrit project name. '
              'Defaults to CUSTOM_PATCHES_GERRIT_PROJECT shell var.')
    )
    parser.add_argument(
        '--new-project',
        default=os.getenv('CUSTOM_PATCHES_NEW_GERRIT_PROJECT'),
        help=('New Gerrit project name. '
              'Defaults to CUSTOM_PATCHES_GERRIT_PROJECT shell var. '
              'If empty, falls back to Gerrit project name.')
    )
    parser.add_argument(
        '--old-branch',
        default=os.getenv('CUSTOM_PATCHES_OLD_BRANCH'),
        help=('Old branch to take patches from (typically, previous release). '
              'Defaults to CUSTOM_PATCHES_OLD_BRANCH shell var')
    )
    parser.add_argument(
        '--new-branch',
        default=os.getenv('CUSTOM_PATCHES_NEW_BRANCH'),
        help=('New branch to push patches to (typically, current release). '
              'Defaults to CUSTOM_PATCHES_OLD_BRANCH shell var')
    )

    parser.add_argument(
        '--long',
        action='store_true',
        help='Print full commit messages'
    )

    parser.add_argument(
        '--json',
        default=None,
        help='Path to JSON output file.'
    )
    parser.add_argument(
        '--regex',
        default=DEFAULT_FILTER_REGEX,
        help=("Output only commits with title matching "
              "this regular expression. "
              "Defaults is mostly suitable for OpenStack projects "
              "and their stable branches. "
              "To output all missing commits, set it to '.*'.")
    )

    args = parser.parse_args()
    if not (args.gerrit_uri and
            args.project and
            args.old_branch and
            args.new_branch):
        parser.error('gerrit-uri, project, old-branch, new-branch '
                     'are required')
    return args


def main():
    logging.basicConfig(
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    LOG.setLevel(logging.INFO)
    args = parse_args()
    repo_path = os.path.basename(args.project)
    repo = prepare_repo(repo_path)
    source_remote, target_remote = update_remotes(
        repo, args.gerrit_uri, args.project,
        new_gerrit_uri=args.new_gerrit_uri,
        new_project=args.new_project)
    missing_changes = find_missing_changes(
        repo, source_remote, target_remote, args.old_branch, args.new_branch)
    output_commits(missing_changes, args.regex,
                   long_out=args.long, json_out=args.json)

if __name__ == '__main__':
    main()