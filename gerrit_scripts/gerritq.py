#!/usr/bin/env python

import json
import pprint
import sys

import requests
from six.moves.urllib_parse import urljoin


OOO_GERRIT_URL = 'https://review.openstack.org'


class GerritQuery(object):

    def __init__(self, url=OOO_GERRIT_URL):
        self.base_url = url

    def changes(self, query):
        url = urljoin(self.base_url, '/changes/?q=%s' % query)
        resp = requests.get(url)
        if resp.ok:
            # sanitize ")]}'" from response
            changes = resp.content[4:]
            return json.loads(changes)
        else:
            return None

if __name__ == '__main__':
    if len(sys.argv) == 1:
        print("Requires query as first argument")
        sys.exit(1)
    pprint.pprint(GerritQuery().changes(sys.argv[1]))
