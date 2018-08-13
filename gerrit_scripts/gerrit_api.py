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

import json

import requests


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


class GerritAdapter(object):
    def __init__(self, session, gerrit_uri, username=None, password=None,
                 **kwargs):
        self.session = session or requests.Session()
        self.url = gerrit_uri
        if password:
            self.session.auth = requests.auth.HTTPDigestAuth(username,
                                                             password)
            self.url += '/a'

    @staticmethod
    def gerrit_response_hook(r, **kwargs):
        """Custom Gerrit response hook for requests lib

        To prevent against Cross Site Script Inclusion (XSSI) attacks,
        the JSON response body returned by Gerrit REST API starts
        with a magic prefix line that must be stripped before feeding
        the rest of the response body to a JSON parser:
            )]}'
            [... valid JSON ...]
        """
        if r.content.startswith(")]}'"):
            r.content = r.content[4:]

    def request(self, url, method, **kwargs):
        if self.url:
            url = self.url + url
        hooks = kwargs.pop('hooks', None) or {
            'response': [self.gerrit_response_hook]}
        return self.session.request(url, method, hooks=hooks, **kwargs)

    def get(self, url, **kwargs):
        return self.request(url, 'GET', **kwargs)

    def head(self, url, **kwargs):
        return self.request(url, 'HEAD', **kwargs)

    def post(self, url, **kwargs):
        return self.request(url, 'POST', **kwargs)

    def put(self, url, **kwargs):
        return self.request(url, 'PUT', **kwargs)

    def patch(self, url, **kwargs):
        return self.request(url, 'PATCH', **kwargs)

    def delete(self, url, **kwargs):
        return self.request(url, 'DELETE', **kwargs)
