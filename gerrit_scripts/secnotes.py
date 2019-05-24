import argparse
import logging
import os
import re
import requests
import sys
import tempfile
import urllib

import git
from lxml import html as lxml_html


LOG = logging.getLogger('secnotes')


STORYBOARD = 'storyboard'
LAUNCHPAD = 'launchpad'
JIRA = 'jira'


STORYBOARD_STORY_LINK = 'https://storyboard.openstack.org/#!/story/'
STORYBOARD_TASK_LINK = 'https://storyboard.openstack.org/#!/task/'
LAUNCHPAD_BUG_LINK = 'https://launchpad.net/bugs/'
JIRA_TASK_LINK = 'https://mirantis.jira.com/browse/'


STORYBOARD_ISSUE_PATTERN = re.compile('Story:\s?#?\d+|Task:\s#?\d+',
                                      re.IGNORECASE)
LAUNCHPAD_ISSUE_PATTERN = re.compile(
    'Closes-Bug:\s?#?\d+|'
    'Close-Bug:\s?#?\d+|'
    'Partial-Bug:\s?#?\d+|'
    'Related-Bug:\s?#?\d+|'
    'Fixes-Bug:\s?#?\d+|'
    'Fix-Bug:\s?#?\d+|',
    re.IGNORECASE)
JIRA_ISSUE_PATTERN = re.compile('PROD-\d+|PROD:\d+', re.IGNORECASE)


TRACKERS_ISSUE_PATTERN_MAP = {
    LAUNCHPAD: LAUNCHPAD_ISSUE_PATTERN,
}


parsed_issues = {
    LAUNCHPAD: {},
    STORYBOARD: {},
    JIRA: {}
}


final_result = []


def parse_args():
    parser = argparse.ArgumentParser(
        description=('Analyze the git log from the start commit sha to '
                     'the end commit sha, extract references to bugs '
                     'and then scan the bug tracker for security issues.')
    )

    parser.add_argument(
        '--gerrit',
        default='https://gerrit.mcp.mirantis.com',
        help=('Gerrit url (full HTTP(S) URL).')
    )
    parser.add_argument(
        '--workdir',
        default=os.path.join(tempfile.gettempdir(), 'secnotes'),
        help=('The directory in which the project will be stored.')
    )
    parser.add_argument(
        '--gerrit-username',
        help=('Gerrit HTTP user name to access Gerrit HTTP API/repos.')
    )
    parser.add_argument(
        '--gerrit-password',
        help=('Gerrit HTTP password.')
    )
    parser.add_argument(
        '--project',
        help=('Gerrit project name.')
    )
    parser.add_argument(
        '--start-commit',
        help=('Start commit SHA which must be before '
              '--end-commit in the log history.')
    )
    parser.add_argument(
        '--end-commit',
        help=('End commit SHA which must be after '
              '--start-commit in the log history.')
    )

    args = parser.parse_args()
    if not args.project:
        parser.error('--project is not specified !')
    if not args.gerrit_username:
        parser.error('--gerrit-username is not specified !')
    if not args.gerrit_password:
        parser.error('--gerrit-password is not specified !')
    if not args.project:
        parser.error('--project is not specified !')
    if not args.start_commit:
        parser.error('--start-commit is not specified !')
    if not args.end_commit:
        parser.error('--end-commit is not specified !')

    return args


def get_repo(gerrit_uri, repo_path):
    if (os.path.exists(repo_path) and
            os.path.isdir(repo_path) and
            os.path.isdir(os.path.join(repo_path, '.git'))):
        LOG.info('Repo %s exists' % repo_path)
        repo = git.Repo(repo_path)
        origin = repo.remotes.origin
        LOG.info('Fetch last updates from the repo')
        origin.fetch()
    else:
        LOG.info('Clonig repo %s' % repo_path)
        repo = git.Repo.clone_from(gerrit_uri,
                                   repo_path,
                                   branch='master')
    return repo


def make_gerrit_repo_url(gerrit_url, project, username=None, password=None):
    auth_string = ''
    if username and password:
        auth_string = '{}:{}@'.format(username,
                                      urllib.parse.quote(password, safe=''))
    url_parts = urllib.parse.urlparse(gerrit_url)
    new_parts = [url_parts[0], '{}{}'.format(auth_string, url_parts[1])]
    new_parts.extend(url_parts[2:])
    repo_url = urllib.parse.urlunparse(new_parts)
    url = urllib.parse.urljoin(repo_url, project)
    return url


def extract_bug_reference(commit):
    for tracker, pattern in TRACKERS_ISSUE_PATTERN_MAP.items():
        results = re.findall(pattern, commit.message)
        results = list(filter(None, results))
        if results:
            parsed_issues[tracker][commit.hexsha] = {
                'title': commit.summary,
                'bugs_ref': []
            }
            for bug_ref in results:
                bug_number = re.search('\d+', bug_ref)
                parsed_issues[tracker][commit.hexsha]['bugs_ref'].append(
                    bug_number.group(0)
                )


def parse_tracker_bug(tracker):
    LOG.info('Trying to crawl trackers for security issues')
    for hexsha, commit_info in parsed_issues[tracker].items():
        for bug_number in commit_info['bugs_ref']:
            if tracker == LAUNCHPAD:
                tracker_link = LAUNCHPAD_BUG_LINK + bug_number
                page = requests.get(tracker_link)
                tree = lxml_html.fromstring(page.content)
                bug_title = tree.xpath('//h1/span')[0].text
                ossa_cve = re.search('\[OSSA-', bug_title)
                if ossa_cve:
                    final_result.append('{hexsha} '
                                        '{commit_title} '
                                        '{tracker_link}'.format(
                                            hexsha=hexsha[:7],
                                            commit_title=commit_info['title'],
                                            tracker_link=tracker_link))
            elif tracker in (STORYBOARD, JIRA):
                raise NotImplementedError("Functionality for tracker {0}"
                                          " isn't implemented".format(tracker))


def main():
    logging.basicConfig(
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    LOG.setLevel(logging.INFO)
    args = parse_args()

    gerrit_uri = make_gerrit_repo_url(args.gerrit,
                                      args.project,
                                      username=args.gerrit_username,
                                      password=args.gerrit_password)

    if not os.path.isdir(args.workdir):
        os.mkdir(args.workdir)
    repo = get_repo(gerrit_uri, os.path.join(args.workdir,
                                             os.path.basename(args.project)))
    commits = repo.iter_commits('{start_commit}^...{end_commit}'.format(
        start_commit=args.start_commit,
        end_commit=args.end_commit), no_merges=True, remove_empty=True)
    LOG.info('Start analyzing commits')
    for commit in commits:
        extract_bug_reference(commit)
    for tracker, _ in TRACKERS_ISSUE_PATTERN_MAP.items():
        parse_tracker_bug(tracker)
    for result in final_result:
        print(result)


if __name__ == '__main__':
    sys.exit(main())
