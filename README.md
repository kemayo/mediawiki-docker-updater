# mediawiki-docker-updater

`update.py` updates a MediaWiki development checkout. It updates MediaWiki core,
all of the skins, and all of the extensions. It runs `composer` and the update
script in the MediaWiki container.

## Before you start

You must have a MediaWiki checkout with the `docker-compose.yml` file that
MediaWiki supplies. The checkout must be MediaWiki 1.40 or later.

Start the container from the MediaWiki checkout:

    docker compose up -d

## How to use the script

The script is not part of the MediaWiki checkout. Run it in one of these two
ways.

Go to the MediaWiki checkout, then give the path to the script:

    cd ~/src/mediawiki
    ~/src/mw-docker-updater/update.py

Or run the script from any directory. Give the path to the MediaWiki checkout as
the argument:

    ~/src/mw-docker-updater/update.py ~/src/mediawiki

If you install the script on your `PATH`, use the name that you gave it. The help
text shows the name `wmf-docker-update`.

## Options

| Option | Function |
| --- | --- |
| `-c NAME`, `--container NAME` | Use a different container. The default name is `mediawiki`. |
| `-f`, `--force-composer` | Run `composer` in each directory that has a `composer.json` file. |
| `-v`, `--verbose` | Show more messages. Use `-vv` to also show the output of each command. |
| `-h`, `--help` | Show the help text. |

## What the script does

For each skin and each extension, the script does two steps:

1. It pulls with `--ff-only`. If the branch has no upstream branch, the script
   does not pull.
2. It runs `composer update` if the dependencies are out of date. See
   [When composer runs](#when-composer-runs).

For core, the script pulls first, before the skins and extensions. It runs
`composer update` in core last, because `composer.local.json` usually merges the
`composer.json` files of the skins and extensions into core.

The script does not pull a directory that is not a Git checkout. It tells you
which directories it does not pull.

At the end, the script runs the MediaWiki update script:

    php maintenance/run.php update --quick

## When composer runs

The script runs `composer update` in a directory if one of these files is newer
than `vendor/composer/installed.json`:

- `composer.json`
- `composer.local.json`
- Each file that `composer.local.json` merges with the merge plugin

The script also runs `composer update` if `vendor/composer/installed.json` is
absent. After a successful run, the script sets the time of that file to now.

Thus the script sees a change from a pull, from a manual pull, from a local edit,
or from an earlier run that failed. The `-f` option makes `composer` run in all
directories.

## If a command fails

The script shows the output of the command that failed. It then continues with
the next directory. At the end, it shows a list of the directories that failed.

The script exits with status 1 if a command failed. If all of the commands are
successful, the script exits with status 0.

## Limits

The script does not run `npm install`. The container has no `npm`. Also, if the
architecture of the container is different from the architecture of your machine,
some packages do not build.
