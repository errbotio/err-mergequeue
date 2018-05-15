#    Copyright 2018 Argo AI, LLC.
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

from github.GithubObject import NotSet
from github.PullRequest import PullRequest
from github.PullRequestMergeStatus import PullRequestMergeStatus
from github import Github  ## Do not remove

## This monkeypatches pygithub.


def edit(self, title=NotSet, body=NotSet, state=NotSet, base=NotSet):
    """
    Original function defined in
    https://github.com/PyGithub/PyGithub/blob/master/github/PullRequest.py
    :calls: `PATCH /repos/:owner/:repo/pulls/:number
    <http://developer.Github.com/v3/pulls>`
    :param title: string
    :param body: string
    :param state: string
    :param base: string
    :rtype: None
    """

    assert title is NotSet or isinstance(title, str), title
    assert body is NotSet or isinstance(body, str), body
    assert state is NotSet or isinstance(state, str), state
    assert base is NotSet or isinstance(base, str), base
    post_parameters = dict()
    if title is not NotSet:
        post_parameters["title"] = title
    if body is not NotSet:
        post_parameters["body"] = body
    if state is not NotSet:
        post_parameters["state"] = state
    if base is not NotSet:
        post_parameters['base'] = base
    headers, data = self._requester.requestJsonAndCheck(
        "PATCH",
        self.url,
        input=post_parameters
    )

    self._useAttributes(data)


PullRequest.edit = edit


def merge(self, commit_message=NotSet, commit_title=NotSet, sha=NotSet, merge_method=NotSet):
    """
    Original function defined in
    https://github.com/PyGithub/PyGithub/blob/master/github/PullRequest.py
    :calls: `PUT /repos/:owner/:repo/pulls/:number/merge
    <http://developer.github.com/v3/pulls>`
    :param commit_message: string
    :param commit_title: string
    :param sha: string
    :param merge_method: string
    :rtype: :class:`github.PullRequestMergeStatus.PullRequestMergeStatus`
    """
    assert commit_message is NotSet or isinstance(commit_message, str), commit_message
    assert commit_title is NotSet or isinstance(commit_title, str), commit_title
    assert sha is NotSet or isinstance(sha, str), sha
    assert merge_method is NotSet or isinstance(merge_method, str), merge_method

    post_parameters = dict()
    if commit_message is not NotSet:
        post_parameters["commit_message"] = commit_message
    if commit_title is not NotSet:
        post_parameters["commit_title"] = commit_title
    if sha is not NotSet:
        post_parameters["sha"] = sha
    if merge_method is not NotSet:
        post_parameters["merge_method"] = merge_method

    headers, data = self._requester.requestJsonAndCheck(
        "PUT",
        self.url + "/merge",
        input=post_parameters
    )
    return PullRequestMergeStatus(self._requester, headers, data,
                                  completed=True)


PullRequest.merge = merge
