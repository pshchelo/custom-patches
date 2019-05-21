
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
import logging
import os
import sys
import urllib.parse

from pygerrit2 import rest


LOG = logging.getLogger('downstream-branch')


def make_gerrit_client(gerrit_uri, gerrit_username=None,
                       gerrit_password=None, digest_auth=False):
    auth = None
    if gerrit_password:
        auth_cls = (rest.auth.HTTPDigestAuth if digest_auth
                    else rest.auth.HTTPBasicAuth)
        auth = auth_cls(gerrit_username, gerrit_password)
    return rest.GerritRestAPI(gerrit_uri, auth=auth)


def find_projects(gerrit, project_prefix, upstream_branch, downstream_branch):
    LOG.info('Listing projects by prefix and branches on Gerrit..')
    u_projs, r = gerrit.get(
        'projects/?p={prefix}&b={branch}'.format(
            prefix=urllib.parse.quote(project_prefix, safe=''),
            branch=urllib.parse.quote(upstream_branch, safe=''),
        ), return_response=True)
    if r.status_code != 200:
        LOG.error('Could not fetch list of projects with prefix {prefix} '
                  'and branch {branch} from URI {url}'.format(
                      url=gerrit.url, prefix=project_prefix,
                      branch=upstream_branch))
        sys.exit(1)
    d_projs, r = gerrit.get(
        'projects/?p={prefix}&b={branch}'.format(
            prefix=urllib.parse.quote(project_prefix, safe=''),
            branch=urllib.parse.quote(downstream_branch, safe=''),
        ), return_response=True)
    if r.status_code != 200:
        LOG.error('Could not fetch list of projects with prefix {prefix} '
                  'and branch {branch} from URI {url}'.format(
                      url=gerrit.url, prefix=project_prefix,
                      branch=downstream_branch))
        sys.exit(1)
    # NOTE(pas-ha) leave only those projects where upstream is present
    # but downstream is absent
    projects = {p: v for p, v in u_projs.items() if (p not in d_projs and
                                                     'patrole' not in p)}
    if not projects:
        LOG.error("No projects found matching prefix and both branches")
        sys.exit(1)
    LOG.info('Projects to create branch on:\n%s' % "\n".join(projects.keys()))
    return projects


def create_branches(gerrit, projects, upstream_branch, downstream_branch,
                    gerrit_password=None, gerrit_username=None, test=False):
    failed = []
    for prj, props in projects.items():
        sha = props['branches'][upstream_branch]
        branch, r = gerrit.put(
            'projects/{project}/branches/{branch}'.format(
                project=urllib.parse.quote(prj, safe=''),
                branch=urllib.parse.quote(downstream_branch, safe=''),
            ),
            json={'revision': sha},
            return_response=True)
        if r.status_code != 201:
            LOG.error('Failed to create branch {branch} on project {prj} '
                      'on gerrit {url}'.format(url=gerrit.url, prj=prj,
                                               branch=downstream_branch))
            failed.append(prj)
        else:
            LOG.info('Created branch {branch} on project {project} from '
                     'commit {sha} on gerrit {url}'.format(
                      url=gerrit.url, project=prj, sha=sha,
                      branch=downstream_branch))
    if failed:
        sys.exit(1)


def parse_args():
    parser = argparse.ArgumentParser(
        prog='downstream-branch',
        description="Bulk create downstream branch on Gerrit from upstream "
        "branch for all projects with given prefix."
    )
    parser.add_argument(
        '--gerrit',
        default=os.getenv('CUSTOM_PATCHES_GERRIT_LOC'),
        help=('Gerrit location (full HTTP(S) URL). '
              'Defaults to CUSTOM_PATCHES_GERRIT_LOC shell var')
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
        '--project-prefix',
        default=os.getenv('CUSTOM_PATCHES_GERRIT_PROJECT_PREFIX'),
        help=('Gerrit project prefix, to fetch all projects starting with it. '
              'Defaults to CUSTOM_PATCHES_GERRIT_PROJECT_PREFIX shell var.')
    )
    parser.add_argument(
        '--upstream-branch',
        default=os.getenv('CUSTOM_PATCHES_UPSTREAM_BRANCH'),
        help=('Old branch (typically, previous release). '
              'If resembling a full-length  SHA, will be considered as '
              'commit SHA instead of a branch name. '
              'Defaults to CUSTOM_PATCHES_UPSTREAM_BRANCH shell var')
    )
    parser.add_argument(
        '--downstream-branch',
        default=os.getenv('CUSTOM_PATCHES_DOWNSTREAM_BRANCH'),
        help=('New branch (typically, current release). '
              'If resembling a full-length  SHA, will be considered as '
              'commit SHA instead of a branch name. '
              'Defaults to CUSTOM_PATCHES_DOWNSTREAM_BRANCH shell var')
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help="Do not actually create branches, "
        "only list the applicable projects"
    )
    return parser.parse_args()


def main():
    logging.basicConfig(
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    LOG.setLevel(logging.INFO)
    args = parse_args()
    gerrit = make_gerrit_client(args.gerrit, args.gerrit_username,
                                args.gerrit_password)
    projects = find_projects(gerrit, args.project_prefix,
                             args.upstream_branch, args.downstream_branch)
    if args.dry_run:
        print("Dry run! Not creating any branches")
        print("Projects found:")
        for p in projects:
            print(p)
    else:
        create_branches(gerrit, projects, args.upstream_branch,
                        args.downstream_branch)


if __name__ == '__main__':
    main()
