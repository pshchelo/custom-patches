import argparse
import json
import os
import re
import sys

import requests

UPSTREAM = 'https://review.opendev.org'
DOWNSTREAM = 'https://gerrit.mcp.mirantis.com/a'
RELEASE = os.getenv("OS_RELEASE", 'pike').lower()


def parse_args():
    parser = argparse.ArgumentParser(
        prog='missing-projects',
        description="Find missing downstream for upstream projects.")
    parser.add_argument(
        'release',
        type=str.lower,
        help='OpenStack release code-name to check (example: ocata)'
    )
    parser.add_argument(
        '--gerrit',
        metavar='GERRIT_URL',
        default=os.getenv('GERRIT_URL', DOWNSTREAM),
        help="Gerrit address."
    )
    parser.add_argument(
        '--user',
        metavar='GERRIT_USER',
        default=os.getenv('GERRIT_USER'),
        help="HTTP Gerrit REST API username."
    )
    parser.add_argument(
        '--password',
        metavar='GERRIT_PASSWORD',
        default=os.getenv('GERRIT_PASSWORD'),
        help="HTTP Gerrit REST API password."
    )
    parser.add_argument(
        '--upstream',
        metavar='UPSTREAM_URL',
        default=os.getenv('UPSTREAM_URL', UPSTREAM),
        help="Upstream Gerrit address."
    )
    return parser.parse_args()


def validate_args(args):
    if not args.password:
        print("gerrit HTTP password is not set, use GERRIT_PASSWORD shell var")
        sys.exit(1)


def main():
    args = parse_args()
    auth = requests.auth.HTTPBasicAuth(args.user, args.password)
    # All downstream specs that have mcp/* branch
    build_specs = json.loads(requests.get(
        '{base}/projects/?p=packaging/specs/&b=mcp/{release}'.format(
            base=args.gerrit, release=args.release),
        auth=auth).text[4:])
    built_downstream = [p.replace('packaging/specs/', '')
                        for p in build_specs.keys()]
    to_append = []
    # add those that have 'python-' w/o such prefix
    for p in built_downstream:
        if p.startswith('python-'):
            to_append.append(p.replace('python-', ''))
    built_downstream.extend(to_append)

    # all upstream projects in openstack/ that have stable/pike branch
    all_upstream = json.loads(requests.get(
        '{base}/projects/?p=openstack/&b=stable/{release}'.format(
            base=args.upstream, release=args.release)).text[4:])
    upstream_projects = [p.replace('openstack/', '')
                         for p in all_upstream.keys()]
    # projects we should be building from at least stable/pike branch
    need_build_upstream = set(built_downstream) & set(upstream_projects)

    # downstream code projects that have stable/pike branch, so are mirrored
    downstream_src = json.loads(requests.get(
        '{base}/projects/?p=packaging/sources/&b=stable/{release}'.format(
            base=args.gerrit, release=args.release),
        auth=auth).text[4:])
    mirrored_downstream = [p.replace('packaging/sources/', '')
                           for p in downstream_src.keys()]

    # projects we may consider start mirroring too
    missing_src = set(need_build_upstream) - set(mirrored_downstream)
    header = "Missing code projects for {release} release".format(
        release=args.release.upper())
    print(header)
    print("="*len(header))
    for l in sorted(missing_src):
        print(l)

    print()
    print()
    print("Looking for all dependencies")
    # parse all missing requirements
    all_reqs = set()
    for prj in need_build_upstream:
        # fetch requirements file
        print("fetching deps for %s" % prj)
        reqs_file = requests.get(
            'https://opendev.org/openstack/{project}/raw/'
            'branch/stable/{release}/requirements.txt'.format(
                project=prj, release=args.release)).text
        # parse and combine requiremnets file
        for r in reqs_file.splitlines():
            if r.startswith('#') or not r:
                continue
            all_reqs.add(re.split('<|>|=|!', r)[0])

    print('=' * 40)
    print("Projects that we miss specs for %s release" % args.release.upper())
    os_deps_projects = (
        set(upstream_projects) & all_reqs) - set(built_downstream)
    for prj in os_deps_projects:
        print(prj)


if __name__ == '__main__':
    sys.exit(main())
