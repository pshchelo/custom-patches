=================================
Find downstream patches in Gerrit
=================================

When dealing with open-source projects in a enterprise world,
it is unfortunately a quite common scenario to have downstream patches
that might be needed to carry over from release to release.

This script is what helps to find those.
It compares two branches from project (possibly hosted on different
Gerrit instances) and finds commits that are missing by comparing
``Change-Id`` inserted into the commit message by the Gerrit git hook.

It also can filter out commits that, although not present in the
new branch/release, are definitely not be carried over
(defaults are targeting peculiarities of OpenStack projects
and development process).

Usage::

    $ python custom_patches.py --help
    usage: custom_patches.py [-h] [--gerrit GERRIT] [--new-gerrit NEW_GERRIT]
                             [--gerrit-username GERRIT_USERNAME]
                             [--new-gerrit-username NEW_GERRIT_USERNAME]
                             [--gerrit-proto {http,https}]
                             [--new-gerrit-proto {http,https}]
                             [--gerrit-ssh-port GERRIT_SSH_PORT]
                             [--new-gerrit-ssh-port NEW_GERRIT_SSH_PORT]
                             [--project PROJECT] [--new-project NEW_PROJECT]
                             [--project-prefix PROJECT_PREFIX]
                             [--gerrit-http-password GERRIT_HTTP_PASSWORD]
                             [--old-branch OLD_BRANCH] [--new-branch NEW_BRANCH]
                             [--long] [--json JSON] [--regex REGEX]

    Using Geriit Change-Id, report patches in <old branch> which are missing in
    the <new branch>. Requires "GitPython" package (pip-)installed from PyPI.

    optional arguments:
      -h, --help            show this help message and exit
      --gerrit GERRIT       Gerrit location. Defaults to CUSTOM_PATCHES_GERRIT_LOC
                            shell var
      --new-gerrit NEW_GERRIT
                            New Gerrit location. Defaults to
                            CUSTOM_PATCHES_NEW_GERRIT_LOC shell var. If empty,
                            falls back to Gerrit location.
      --gerrit-username GERRIT_USERNAME
                            Gerrit URI. Defaults to CUSTOM_PATCHES_GERRIT_USERNAME
                            shell var
      --new-gerrit-username NEW_GERRIT_USERNAME
                            New Gerrit repo URI. Defaults to
                            CUSTOM_PATCHES_NEW_GERRIT_USERNAME shell var. If
                            empty, falls back to Gerrit username.
      --gerrit-proto {http,https}
                            Protocol to access Gerrit's REST API
      --new-gerrit-proto {http,https}
                            Protocol to access new Gerrit's REST API
      --gerrit-ssh-port GERRIT_SSH_PORT
                            Port to access Gerrit's SSH API
      --new-gerrit-ssh-port NEW_GERRIT_SSH_PORT
                            Port to access Gerrit's SSH API
      --project PROJECT     Gerrit project name. Defaults to
                            CUSTOM_PATCHES_GERRIT_PROJECT shell var.
      --new-project NEW_PROJECT
                            New Gerrit project name. Defaults to
                            CUSTOM_PATCHES_NEW_GERRIT_PROJECT shell var. If empty,
                            falls back to Gerrit project name.
      --project-prefix PROJECT_PREFIX
                            Gerrit project name. Defaults to
                            CUSTOM_PATCHES_GERRIT_PROJECT_PREFIX shell var.
      --gerrit-http-password GERRIT_HTTP_PASSWORD
                            Gerrit HTTP password. Defaults to
                            CUSTOM_PATCHES_GERRIT_HTTP_PASSWORD shell var.
      --old-branch OLD_BRANCH
                            Old branch (typically, previous release). Defaults to
                            CUSTOM_PATCHES_OLD_BRANCH shell var
      --new-branch NEW_BRANCH
                            New branch (typically, current release). Defaults to
                            CUSTOM_PATCHES_OLD_BRANCH shell var
      --long                Print full commit messages
      --json JSON           Path to JSON output file. Default is not to generate
                            JSON output.
      --regex REGEX         Output only commits with title matching this regular
                            expression. Default "^(?!(Updated from global
                            requirements|Imported Translations from Zanata))" is
                            mostly suitable for OpenStack projects and their
                            stable branches. To output all missing commits, set it
                            to '.*'.
