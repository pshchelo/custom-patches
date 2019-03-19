import json
import os
import re
import sys

import requests

UPSTREAM = 'https://review.openstack.org'
DOWNSTREAM = 'https://gerrit.mcp.mirantis.com/a'
RELEASE = os.getenv("OS_RELEASE", 'pike').lower()


def main():
    gerrit_password = os.getenv('GERRIT_PASSWORD')
    if not gerrit_password:
        print("gerrit HTTP password is not set, use GERRIT_PASSWORD shell var")
        sys.exit(1)

    auth = requests.auth.HTTPBasicAuth(username=os.getenv('GERRIT_USER',
                                                          'pshchelokovskyy'),
                                       password=gerrit_password)
    # All downstream specs that have mcp/* branch
    build_specs = json.loads(requests.get(
        '{base}/projects/?p=packaging/specs/&b=mcp/{release}'.format(
            base=DOWNSTREAM, release=RELEASE),
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
            base=UPSTREAM, release=RELEASE)).text[4:])
    upstream_projects = [p.replace('openstack/', '')
                         for p in all_upstream.keys()]
    # projects we should be building from at least stable/pike branch
    need_build_upstream = set(built_downstream) & set(upstream_projects)

    # downstream code projects that have stable/pike branch, so are mirrored
    downstream_src = json.loads(requests.get(
        '{base}/projects/?p=packaging/sources/&b=stable/{release}'.format(
            base=DOWNSTREAM, release=RELEASE),
        auth=auth).text[4:])
    mirrored_downstream = [p.replace('packaging/sources/', '')
                           for p in downstream_src.keys()]

    # projects we may consider start mirroring too
    missing_src = set(need_build_upstream) - set(mirrored_downstream)
    header = "Missing code projects for {release} release".format(
        release=RELEASE.upper())
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
            'http://git.openstack.org/cgit/openstack/{project}/plain/'
            'requirements.txt?h=stable/{release}'.format(
                project=prj, release=RELEASE)).text
        # parse and combine requiremnets file
        for r in reqs_file.splitlines():
            if r.startswith('#') or not r:
                continue
            all_reqs.add(re.split('<|>|=|!', r)[0])

    print('=' * 40)
    print("Projects that we miss specs for %s release" % RELEASE.upper())
    os_deps_projects = (
        set(upstream_projects) & all_reqs) - set(built_downstream)
    for prj in os_deps_projects:
        print(prj)
