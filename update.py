#!/usr/bin/env python3

import os
import sys
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


def update_directory(directory, container, verbose=0):
    """Update one checkout. Returns False if a command failed."""
    try:
        # TODO: fetch first and diff composer.json, so composer can be skipped
        # when the manifest did not change. That is where the runtime goes.
        if has_upstream(directory):
            printif(verbose > 0, ' > git pull')
            # --ff-only: a merge commit here is never what we want.
            run(['git', '-C', directory, 'pull', '--ff-only'], verbose=verbose)
        else:
            # A patch under review sits on a detached HEAD. Leave it alone, but
            # still refresh its dependencies.
            print(f'SKIP: {directory} has no upstream branch, not pulling')
        if os.path.exists(os.path.join(directory, 'composer.json')):
            printif(verbose > 0, ' > composer update')
            docker_cmd(
                directory, container, 'composer', 'update', verbose=verbose
            )
        # npm is not on the container, and is less essential anyway -- it's
        # mostly for dev tools in this ecosystem. Main reason to not run it
        # locally is that if the container's on a different architecture, any
        # packages that need to build from source will presumably break
        # log.info('npm install') docker_cmd
        # (directory, container, 'npm', 'install')
    except subprocess.CalledProcessError as e:
        print('ERROR: Failed to update', directory)
        report_failure(e)
        return False
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
        usage='wmf-docker-update [-h] [-c CONTAINER] [-v] [directory]',
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    ap.add_argument('-c', '--container', default='mediawiki')
    ap.add_argument('--verbose', '-v', action='count', default=0)
    ap.add_argument('directory', nargs='?')
    args = ap.parse_args()

    # Subprocesses write straight to the pipe, so our labels must not sit in a
    # buffer behind them when the output is redirected.
    sys.stdout.reconfigure(line_buffering=True)

    if args.directory:
        print(f'Changing working directory to {args.directory}')
        os.chdir(args.directory)

    failed = []

    print('Updating mediawiki')
    if not update_directory('.', args.container, verbose=args.verbose):
        failed.append('.')

    for directory in [*checkouts('skins'), *checkouts('extensions')]:
        print(f'Updating {directory}')
        if not update_directory(
            directory, args.container, verbose=args.verbose
        ):
            failed.append(directory)

    # Still worth running even after failures: whatever did update may need it.
    print('Running maintenance update')
    try:
        docker_cmd(
            '.', args.container, 'php', 'maintenance/update.php', '--quick',
            verbose=args.verbose
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
