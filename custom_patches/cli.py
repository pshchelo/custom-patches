# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import collections
import json
import logging
import os
import re
import sys
import urllib.parse

import git
import requests

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
    source.update(prune=True)
    if source_remote != target_remote:
        new_gerrit_repo = os.path.join(new_gerrit_uri, new_project.strip('/'))
        if target_remote in (r.name for r in repo.remotes):
            target = repo.remotes[target_remote]
            target.set_url(new_gerrit_repo)
        else:
            target = repo.create_remote(target_remote, new_gerrit_repo)
        LOG.info("Fetching from remote %s" % new_gerrit_repo)
        target.update(prune=True)

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


def output_commits(all_commits, filter_regex_str, long_out=False,
                   json_out=None):
    filter_regex = re.compile(filter_regex_str)
    commit_dict = collections.defaultdict(lambda: {})

    for prj, commits in all_commits.items():
        header = "Project: {proj}".format(proj=prj)
        print('\n'+header+'\n'+'='*len(header))
        for c in commits:
            commit_lines = c.message.splitlines()
            title = commit_lines[0]
            message = commit_lines[1:]
            if filter_regex.match(title):
                print("{id} {title}".format(id=c.hexsha[:8],
                                            title=title.encode('utf-8')))
                if long_out:
                    for l in message:
                        print(" " * 9 + l)
                    print("\n")
                if json_out:
                    commit_dict[prj][c.hexsha] = {'title': title,
                                                  'message': message}

    if commit_dict:
        LOG.info("Writing JSON output to %s" % json_out)
        with open(json_out, 'w') as out:
            json.dump(commit_dict, out, indent=4)


class GerritJSONDecoder(json.JSONDecoder):
    """Custom JSON decoder for Gerrit API respones.

    To prevent against Cross Site Script Inclusion (XSSI) attacks,
    the JSON response body returned by Gerrit REST API starts
    with a magic prefix line that must be stripped before feeding
    the rest of the response body to a JSON parser:
        )]}'
        [... valid JSON ...]
    """
    def decode(self, s):
        return super(GerritJSONDecoder, self).decode(s[4:])


def make_gerrit_api_url(args):
    return "{scheme}://{loc}".format(scheme=args.gerrit_proto,
                                     loc=args.gerrit)


def make_gerrit_ssh_uris(args):
    gerrit_ssh = "ssh://{user}@{loc}:{port}".format(
        user=args.gerrit_username,
        loc=args.gerrit,
        port=args.gerrit_ssh_port)
    if not args.new_gerrit:
        new_gerrit_ssh = None
    else:
        new_gerrit_ssh = "ssh://{user}@{loc}:{port}".format(
            user=args.new_gerrit_username,
            loc=args.new_gerrit,
            port=args.new_gerrit_ssh_port)
    return gerrit_ssh, new_gerrit_ssh


def find_projects(gerrit_uri, project_prefix, old_branch, new_branch,
                  gerrit_password=None, gerrit_username=None):
    session = requests.Session()
    if gerrit_password:
        session.auth = requests.auth.HTTPDigestAuth(gerrit_username,
                                                    gerrit_password)
        gerrit_uri += '/a'

    r = session.get('{url}/projects/?p={prefix}'.format(
        url=gerrit_uri, prefix=urllib.parse.quote(project_prefix, safe='')))
    if r.status_code != 200:
        LOG.error('Could not fetch list of projects with prefix {prefix} '
                  'from URI {url}'.format(url=gerrit_uri,
                                          prefix=project_prefix))
        sys.exit(1)
    projects = r.json(cls=GerritJSONDecoder)
    found = []
    for proj in projects:
        r = session.get('{url}/projects/{project}/branches'.format(
            url=gerrit_uri, project=urllib.parse.quote(proj, safe='')))
        if r.status_code != 200:
            LOG.warning('Failed to list branches for project {project} '
                        'on remote {url}'.format(project=proj, url=gerrit_uri))
            continue

        if all('refs/heads/'+b in map(lambda x: x['ref'],
                                      r.json(cls=GerritJSONDecoder))
               for b in (old_branch, new_branch)):
            found.append(proj)
    LOG.info('Projects to fetch: %s' % found)
    return found


def parse_args():
    parser = argparse.ArgumentParser(
        description=('Using Geriit Change-Id, report patches in <old branch> '
                     'which are missing in the <new branch>. ')
    )
    parser.add_argument(
        '--gerrit',
        default=os.getenv('CUSTOM_PATCHES_GERRIT_LOC'),
        help=('Gerrit location. '
              'Defaults to CUSTOM_PATCHES_GERRIT_LOC shell var')
    )
    parser.add_argument(
        '--new-gerrit',
        default=os.getenv('CUSTOM_PATCHES_NEW_GERRIT_LOC'),
        help=('New Gerrit location. '
              'Defaults to CUSTOM_PATCHES_NEW_GERRIT_LOC shell var. '
              'If empty, falls back to Gerrit location.')
    )
    parser.add_argument(
        '--gerrit-username',
        default=os.getenv('CUSTOM_PATCHES_GERRIT_USERNAME'),
        help=('Gerrit URI. '
              'Defaults to CUSTOM_PATCHES_GERRIT_USERNAME shell var')
    )
    parser.add_argument(
        '--new-gerrit-username',
        default=os.getenv('CUSTOM_PATCHES_NEW_GERRIT_USERNAME'),
        help=('New Gerrit repo URI. '
              'Defaults to CUSTOM_PATCHES_NEW_GERRIT_USERNAME shell var. '
              'If empty, falls back to Gerrit username.')
    )
    parser.add_argument(
        '--gerrit-proto',
        default='https', choices=('http', 'https'),
        help=("Protocol to access Gerrit's REST API")
    )
    parser.add_argument(
        '--new-gerrit-proto',
        default='https', choices=('http', 'https'),
        help=("Protocol to access new Gerrit's REST API")
    )
    parser.add_argument(
        '--gerrit-ssh-port',
        default=29418, type=int,
        help=("Port to access Gerrit's SSH API")
    )
    parser.add_argument(
        '--new-gerrit-ssh-port',
        default=29418, type=int,
        help=("Port to access Gerrit's SSH API")
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
              'Defaults to CUSTOM_PATCHES_NEW_GERRIT_PROJECT shell var. '
              'If empty, falls back to Gerrit project name.')
    )
    parser.add_argument(
        '--project-prefix',
        default=os.getenv('CUSTOM_PATCHES_GERRIT_PROJECT_PREFIX'),
        help=('Gerrit project name. '
              'Defaults to CUSTOM_PATCHES_GERRIT_PROJECT_PREFIX shell var.')
    )
    parser.add_argument(
        '--gerrit-http-password',
        default=os.getenv('CUSTOM_PATCHES_GERRIT_HTTP_PASSWORD'),
        help=('Gerrit HTTP password. '
              'Defaults to CUSTOM_PATCHES_GERRIT_HTTP_PASSWORD shell var.')
    )
    parser.add_argument(
        '--old-branch',
        default=os.getenv('CUSTOM_PATCHES_OLD_BRANCH'),
        help=('Old branch (typically, previous release). '
              'Defaults to CUSTOM_PATCHES_OLD_BRANCH shell var')
    )
    parser.add_argument(
        '--new-branch',
        default=os.getenv('CUSTOM_PATCHES_NEW_BRANCH'),
        help=('New branch (typically, current release). '
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
        help=('Path to JSON output file. '
              'Default is not to generate JSON output.')
    )
    parser.add_argument(
        '--regex',
        default=DEFAULT_FILTER_REGEX,
        help=("Output only commits with title matching "
              "this regular expression. "
              "Default \"%s\" is mostly suitable for OpenStack projects "
              "and their stable branches. "
              "To output all missing commits, set it to '.*'."
              % DEFAULT_FILTER_REGEX)
    )

    args = parser.parse_args()
    if not (args.gerrit and args.gerrit_username and
            (args.project or args.project_prefix) and
            args.old_branch and args.new_branch):
        parser.error('gerrit, project or project-prefix, '
                     'old-branch, new-branch are required')
    return args


def main():
    logging.basicConfig(
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    LOG.setLevel(logging.INFO)
    args = parse_args()
    all_missing = {}
    if args.project_prefix:
        api_url = make_gerrit_api_url(args)
        found = find_projects(api_url, args.project_prefix,
                              args.old_branch, args.new_branch,
                              gerrit_password=args.gerrit_http_password,
                              gerrit_username=args.gerrit_username)
        projects = zip(found, [None]*len(found))
    else:
        projects = [(args.project, args.new_project)]
    if projects:
        gerrit_uri, new_gerrit_uri = make_gerrit_ssh_uris(args)
        for project, new_project in projects:
            repo = prepare_repo(os.path.basename(project))
            source_remote, target_remote = update_remotes(
                repo, gerrit_uri, project,
                new_gerrit_uri=new_gerrit_uri,
                new_project=args.new_project)
            all_missing[new_project or project] = find_missing_changes(
                repo, source_remote, target_remote, args.old_branch,
                args.new_branch)
        output_commits(all_missing, args.regex,
                       long_out=args.long, json_out=args.json)
