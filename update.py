#!/usr/bin/env python3

import os
import sys
import glob
import json
import signal
import subprocess
import argparse

DOCKER_ROOT = '/var/www/html/w'


def run(cmd, verbose=0):
    # Output is captured so it can be replayed only when a command fails. At
    # -vv it goes straight to the terminal instead, so there is nothing to
    # replay.
    subprocess.run(cmd, check=True, capture_output=verbose <= 1, text=True)


def docker_cmd(directory, container, *args, verbose=0):
    cmd = [
        # -T because compose allocates a TTY by default, which fails when
        # stdin is not a terminal (cron, pipes).
        'docker', 'compose', 'exec', '-T',
        '-w', os.path.join(DOCKER_ROOT, directory), container
    ]
    cmd.extend(args)
    run(cmd, verbose=verbose)


def printif(condition, *args, **kwargs):
    if condition:
        print(*args, **kwargs)


def has_upstream(directory):
    return subprocess.run(
        ['git', '-C', directory, 'rev-parse', '--verify', '--quiet', '@{u}'],
        capture_output=True
    ).returncode == 0


def composer_manifests(directory):
    """The files that the vendor directory is built from."""
    manifests = [os.path.join(directory, 'composer.json')]
    local = os.path.join(directory, 'composer.local.json')
    if not os.path.exists(local):
        return manifests
    manifests.append(local)
    try:
        with open(local) as f:
            merge = json.load(f).get('extra', {}).get('merge-plugin', {})
    except (OSError, ValueError, AttributeError):
        # Composer reports the problem when it runs, and the edit that caused
        # it makes the file newer than the vendor directory.
        return manifests
    for pattern in merge.get('include', []) + merge.get('require', []):
        manifests.extend(glob.glob(os.path.join(directory, pattern)))
    return manifests


def needs_composer(directory, force=False):
    """Whether composer has anything to do in this directory."""
    # Checked before force, because composer cannot run without a manifest.
    if not os.path.exists(os.path.join(directory, 'composer.json')):
        return False
    if force:
        return True
    # Compare against the state on disk, not against what this run pulled, so
    # that a manual pull, a local edit or an earlier failed run is seen too.
    try:
        installed = os.path.getmtime(installed_json(directory))
    except FileNotFoundError:
        return True
    return any(
        os.path.getmtime(manifest) > installed
        for manifest in composer_manifests(directory)
    )


def installed_json(directory):
    return os.path.join(directory, 'vendor', 'composer', 'installed.json')


def mark_composer_done(directory):
    # Composer does not write installed.json when no package changes. Without
    # this, a manifest change that has no effect on packages makes composer
    # run again on each update.
    try:
        os.utime(installed_json(directory))
    except OSError:
        pass


def checkouts(parent):
    """Yield the git checkouts directly inside parent."""
    try:
        names = sorted(f.name for f in os.scandir(parent) if f.is_dir())
    except FileNotFoundError:
        return
    for name in names:
        directory = os.path.join(parent, name)
        # .git is a file, not a directory, in worktrees and submodules.
        if os.path.exists(os.path.join(directory, '.git')):
            yield directory
        else:
            print(f'SKIP: {directory} is not a git checkout')


def pull_directory(directory, verbose=0):
    """Pull one checkout. Returns False if the pull failed."""
    if not has_upstream(directory):
        # A patch under review sits on a detached HEAD. Leave it alone, but
        # still consider its dependencies.
        print(f'SKIP: {directory} has no upstream branch, not pulling')
        return True
    printif(verbose > 0, ' > git pull')
    try:
        # --ff-only: a merge commit here is never what we want.
        run(['git', '-C', directory, 'pull', '--ff-only'], verbose=verbose)
    except subprocess.CalledProcessError as e:
        print('ERROR: Failed to pull', directory)
        report_failure(e)
        return False
    return True


def composer_directory(directory, container, verbose=0, force=False):
    """Run composer in one checkout if needed. Returns False if it failed."""
    if not needs_composer(directory, force):
        printif(verbose > 0, ' > composer not needed')
        return True
    printif(verbose > 0, ' > composer update')
    try:
        docker_cmd(directory, container, 'composer', 'update', verbose=verbose)
    except subprocess.CalledProcessError as e:
        print('ERROR: Failed to run composer in', directory)
        report_failure(e)
        return False
    mark_composer_done(directory)
    # npm is not on the container, and is less essential anyway -- it's
    # mostly for dev tools in this ecosystem. Main reason to not run it
    # locally is that if the container's on a different architecture, any
    # packages that need to build from source will presumably break
    # log.info('npm install') docker_cmd
    # (directory, container, 'npm', 'install')
    return True


def report_failure(e):
    # Both are None at -vv, where the output was not captured.
    for stream in (e.stdout, e.stderr):
        if stream and stream.strip():
            print(stream.strip())


def main():
    description = """Update a mediawiki checkout and all its extensions and skins

    This will run relevant commands through the official docker container"""
    ap = argparse.ArgumentParser(
        usage='wmf-docker-update [-h] [-c CONTAINER] [-f] [-v] [directory]',
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    ap.add_argument('-c', '--container', default='mediawiki')
    ap.add_argument(
        '-f', '--force-composer', action='store_true',
        help='run composer everywhere, even where nothing appears to need it'
    )
    ap.add_argument('--verbose', '-v', action='count', default=0)
    ap.add_argument('directory', nargs='?')
    args = ap.parse_args()

    # Subprocesses write straight to the pipe, so our labels must not sit in a
    # buffer behind them when the output is redirected.
    sys.stdout.reconfigure(line_buffering=True)
    # Python ignores SIGPIPE and raises instead, which turns "update.py | head"
    # into a traceback. Restore the default, so the script stops quietly like
    # any other command in a pipeline.
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)

    if args.directory:
        print(f'Changing working directory to {args.directory}')
        os.chdir(args.directory)

    failed = []

    print('Updating mediawiki')
    if not pull_directory('.', verbose=args.verbose):
        failed.append('.')

    for directory in [*checkouts('skins'), *checkouts('extensions')]:
        print(f'Updating {directory}')
        if not (
            pull_directory(directory, verbose=args.verbose)
            and composer_directory(
                directory, args.container, verbose=args.verbose,
                force=args.force_composer
            )
        ):
            failed.append(directory)

    # After the extensions and skins, because composer.local.json usually
    # merges their composer.json files into the core vendor directory.
    print('Updating mediawiki dependencies')
    if not composer_directory(
        '.', args.container, verbose=args.verbose, force=args.force_composer
    ) and '.' not in failed:
        failed.append('.')

    # Still worth running even after failures: whatever did update may need it.
    print('Running maintenance update')
    try:
        # run.php is the supported entry point since 1.40. Calling the script
        # directly still works, but warns.
        docker_cmd(
            '.', args.container, 'php', 'maintenance/run.php', 'update',
            '--quick', verbose=args.verbose
        )
    except subprocess.CalledProcessError as e:
        print('ERROR: Failed to run maintenance update')
        report_failure(e)
        return 1

    if failed:
        print(f'ERROR: {len(failed)} of these failed to update:')
        for directory in failed:
            print(f'  {directory}')
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
