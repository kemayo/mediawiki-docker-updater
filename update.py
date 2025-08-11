#!/usr/bin/env python3

import os
import sys
import subprocess
import argparse

DOCKER_ROOT = '/var/www/html/w'


def docker_cmd(directory, container, *args, verbose=0):
    cmd = [
        'docker-compose', 'exec',
        '-w', os.path.join(DOCKER_ROOT, directory), container
    ]
    cmd.extend(args)
    subprocess.run(
        cmd,
        check=True,
        capture_output=verbose <= 1
    )


def printif(condition, *args, **kwargs):
    if condition:
        print(*args, *kwargs)


def update_directory(directory, container, verbose=0):
    try:
        # TODO: this could be a lot smarter. If we git fetch and then git diff
        # to scan for actual changes to composer.json, we could avoid calling
        # composer when it's not needed.
        # We could also check whether there's a remote tracking branch rather
        # than just letting the pull fail:
        # subprocess.check_call([
        #    'git', '-C', directory, 'rev-parse', '--symbolic-full-name',
        #    '--abbrev-ref', '@{u}'
        # ])
        printif(verbose > 0, ' > git pull')
        subprocess.run(
            ['git', '-C', directory, 'pull'],
            check=True,
            capture_output=verbose <= 1
        )
        printif(verbose > 0, ' > composer update')
        docker_cmd(directory, container, 'composer', 'update', verbose=verbose)
        # This isn't on the container, and is less essential anyway -- it's
        # mostly for dev tools in this ecosystem. Main reason to not run it
        # locally is that if the container's on a different architecture, any
        # packages that need to build from source will presumably break
        # log.info('npm install') docker_cmd
        # (directory, container, 'npm', 'install')
    except subprocess.CalledProcessError:
        print('ERROR: Failed to update %s', directory)


def main():
    description = """Update a mediawiki checkout and all its extensions and skins

    This will run relevant commands through the official docker container"""
    ap = argparse.ArgumentParser(
        usage='wmf-docker-update [-h] [directory]',
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    ap.add_argument('-c', '--container', default='mediawiki')
    ap.add_argument('--verbose', '-v', action='count', default=0)
    ap.add_argument('directory', nargs='*')
    args = ap.parse_args()

    if len(args.directory) > 0:
        print(f'Changing working directory to {args.directory[0]}')
        os.chdir(args.directory[0])

    print('Updating mediawiki')
    update_directory('.', args.container, verbose=args.verbose)

    for skin in [f.name for f in os.scandir('skins') if f.is_dir()]:
        print(f'Updating skins/{skin}')
        update_directory(
            os.path.join('skins', skin), args.container,
            verbose=args.verbose
        )

    for extension in [f.name for f in os.scandir('extensions') if f.is_dir()]:
        print(f'Updating extensions/{extension}')
        update_directory(
            os.path.join('extensions', extension), args.container,
            verbose=args.verbose
        )

    print('Running maintenance update')
    docker_cmd(
        '.', args.container, 'php', 'maintenance/update.php', '--quick',
        verbose=args.verbose
    )


if __name__ == '__main__':
    sys.exit(main())
