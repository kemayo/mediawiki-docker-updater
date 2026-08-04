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

For core, and then for each skin and each extension, the script does two steps:

1. It pulls with `--ff-only`. If the branch has no upstream branch, the script
   does not pull.
2. It runs `composer update`. It does this only if the pull changed the
   `composer.json` file, or if the `vendor` directory is absent. The `-f` option
   makes `composer` run in all directories.

The script does not pull a directory that is not a Git checkout. It tells you
which directories it does not pull.

At the end, the script runs the MediaWiki update script:

    php maintenance/run.php update --quick

## If a command fails

The script shows the output of the command that failed. It then continues with
the next directory. At the end, it shows a list of the directories that failed.

The script exits with status 1 if a command failed. If all of the commands are
successful, the script exits with status 0.

## Limits

The script finds a change to a `composer.json` file only if the pull supplies
that change. Use the `-f` option in these two conditions:

- You changed a `composer.json` file yourself.
- You changed the `composer.local.json` file. Git does not record that file, so
  the script cannot see the change.

The script does not run `npm install`. The container has no `npm`. Also, if the
architecture of the container is different from the architecture of your machine,
some packages do not build.
