[![CI Status](https://img.shields.io/travis/errbotio/err-mergequeue/master.svg)](https://travis-ci.org/errbotio/err-mergequeue/)
[![License: MIT](https://img.shields.io/badge/License-Apachev2-yellow.svg)](https://choosealicense.com/licenses/apache-2.0/#)

This is a chat based Github merge queue plugin for Errbot.

## Base setup

1. Deploy an instance of Errbot if you don't have one already. See [here](http://errbot.io/en/latest/user_guide/setup.html).

2. Talking to Errbot privately as a bot administrator, install the plugin repo for mergequeue.
```
!repos install https://github.com/argoai/err-mergequeue
```

3. Create a github API key for example create a user for the bot and generate a [personal token](https://github.com/settings/tokens).

4. Still talking to Errbot privately as a bot administrator, set the github key with:

```
!plugin config Merge {'github-token': 'cafecafecafecafecafecafecafecafecafecafe'}
```

5. Issuing `!help` should give you a new set of commands related to mergequeue.

## Linking a repo to a chat room/channel

You need to be in the channel you want to setup the repo in and pass it on as a parameter for `!merge config` for
example:

```
!merge config errbotio/errbot
```

## adding saints

Saints are people that can "bless" PRs on the queue. We made this feature as a "last check" before merge.
The person identifier needs to be in the recognized format for the chat backend ie starting with @ for example with Slack.

```
!merge canonize @gbin
```

## Basic workflow

A user can add a PR at the bottom of the queue with `!merge ask`

```
!merge ask 123
```

A saint can bless the PR.
```
!merge bless 123
```

The bot will merge the base of the PR into the PR to put it up to date (and possibly trigger a CI build).
Once the PR is meeting all the requirements set on github to be merged, it will merge it.

## More ...

You can bump PRs on the queue, change the cumber of concurrent updated PRs, etc...
Checkout `!help` for more.


