from typing import List
import importlib
from mergequeue import MergeQueue, MergeQueueException
from pr import PR, PRTransition
from stats import NoStats
import github_wrapper
import pytest


class FakeGHUser:
    def __init__(self, login:str='gbinet-argo'):
        self.login = login


PENDING = 'PENDING'
REQUEST_CHANGES = 'REQUEST_CHANGES'
CHANGES_REQUESTED = 'CHANGES_REQUESTED'
APPROVED = 'APPROVED'
COMMENTED = "COMMENTED"


class FakeGHReview:
    def __init__(self, login: str='rkeelan', state: str = APPROVED):
        self.user = FakeGHUser(login)
        self.state = state

# State
OPEN = 'open'
CLOSED = 'closed'

# Mergeable state
CLEAN = 'clean'
BEHIND = 'behind'
BLOCKED = 'blocked'
UNKNOWN = 'unknown'
DIRTY = 'dirty'


class FakeGHRef:
    def __init__(self, ref='develop'):
        self.ref = ref


class FakeGHPullRequest:
    def __init__(self,
                 number=12,
                 user=FakeGHUser(),
                 state=OPEN,
                 merged=False,
                 mergeable=False,
                 mergeable_state=BLOCKED,
                 body='Some stuff',
                 reviews: List[FakeGHReview]=None,
                 head=None,
                 base=None,
                 title="New Pull Request"):
        self.number = number
        self.user = user
        self.html_url = f'https://github.com/argoai/av/pull/{number}'
        self.state = state
        self.reviews = reviews if reviews else []
        self.mergeable = mergeable
        self.mergeable_state = mergeable_state
        self.body = body
        self.head = head if head else FakeGHRef(f'feature/stuff_{number}')
        self.base = base if base else FakeGHRef()
        self.merged = merged
        self.asked_to_be_merged = False  # Track if the system tried to merge it
        self.title = title

    def get_reviews(self):
        return self.reviews

    def merge(self, commit_title=None):
        self.asked_to_be_merged = True

    def add_review(self, review):
        self.reviews.append(review)

    def __hash__(self):
        return self.number

    def __eq__(self, other):
        if type(other) is not PR:
            return other == self.number  # so you can find them by number
        return other.number == self.number


class FakeGHRepo:
    def __init__(self, injected_prs: List[FakeGHPullRequest]=None):
        self.injected_prs = injected_prs if injected_prs else {}
        self.merge_requests = []

    def get_pull(self, pr_nb):
        # if we have a precise desire fullfill it...
        if pr_nb in self.injected_prs:
            return self.injected_prs[self.injected_prs.index(pr_nb)]

        # ... or just invent it
        return FakeGHPullRequest(number=pr_nb)

    def get_pulls(self, base=None):
        return []

    def merge(self, base=None, head=None):
        self.merge_requests.append((base, head))
        return True


@pytest.fixture(autouse=True)
def no_requests(monkeypatch):
    monkeypatch.setattr(github_wrapper, 'PullRequest', FakeGHPullRequest)


def test_init():
    mq = MergeQueue(FakeGHRepo())
    assert mq.get_queue() == []


def test_getpr():
    mq = MergeQueue(FakeGHRepo())
    pr, gh_pr = mq.get_pr(12)
    assert pr.nb == 12
    assert gh_pr.number == 12


def test_askpr():
    mq = MergeQueue(FakeGHRepo())
    mq.ask_pr(13)
    assert len(mq.queue) == 1
    assert mq.queue[0].nb == 13
    with pytest.raises(MergeQueueException):
        mq.ask_pr(13)
    assert len(mq.queue) == 1


def test_askpr_closed():
    repo = FakeGHRepo(injected_prs=[FakeGHPullRequest(14, state=CLOSED)])
    mq = MergeQueue(repo)
    with pytest.raises(MergeQueueException):
        mq.ask_pr(14)
    assert len(mq.queue) == 0


def test_simple_rmpr():
    mq = MergeQueue(FakeGHRepo())
    mq.ask_pr(12)
    assert len(mq.queue) == 1

    mq.rm_pr(12)
    assert len(mq.queue) == 0

    with pytest.raises(MergeQueueException):
        mq.rm_pr(14)


def test_bless_pr():
    mq = MergeQueue(FakeGHRepo())
    mq.ask_pr(12)
    mq.bless_pr(12)
    assert mq.queue[0].blessed

    with pytest.raises(MergeQueueException):
        mq.bless_pr(13)


def test_excommunicate_pr():
    mq = MergeQueue(FakeGHRepo())
    mq.ask_pr(12)
    mq.bless_pr(12)
    assert mq.queue[0].blessed
    mq.excommunicate_pr(12)
    assert not mq.queue[0].blessed

    with pytest.raises(MergeQueueException):
        mq.excommunicate_pr(13)


def test_bump_pr():
    mq = MergeQueue(FakeGHRepo())
    mq.ask_pr(12)
    mq.ask_pr(13)
    assert mq.queue[0].nb == 12
    with pytest.raises(MergeQueueException):
        mq.bump_pr(13)
    mq.bless_pr(13)
    mq.bump_pr(13)
    assert mq.queue[0].nb == 13
    assert mq.queue[1].nb == 12
    assert mq.pulled_prs[0] == 13
    with pytest.raises(MergeQueueException):
        mq.bump_pr(14)


def test_sink_pr():
    mq = MergeQueue(FakeGHRepo())
    mq.ask_pr(12)
    mq.ask_pr(13)
    assert mq.queue[0].nb == 12
    mq.sink_pr(12)
    assert mq.queue[0].nb == 13
    assert mq.queue[1].nb == 12

    with pytest.raises(MergeQueueException):
        mq.sink_pr(14)


def test_check_review_counting():
    pr_14 = FakeGHPullRequest(14)
    repo = FakeGHRepo(injected_prs=[pr_14])
    mq = MergeQueue(repo)
    mq.ask_pr(14)
    transitions = list(mq.check())
    assert len(transitions) == 0  # nothing changed so nothing should happen

    pr_14.reviews.append(FakeGHReview('dugenou', APPROVED))

    transitions = list(mq.check())
    assert len(transitions) == 1
    pr, [(transition, params)] = transitions[0]
    assert transition == PRTransition.GOT_POSITIVE

    pr_14.reviews.append(FakeGHReview('dugland', CHANGES_REQUESTED))

    transitions = list(mq.check())
    assert len(transitions) == 1
    pr, [(transition, params)] = transitions[0]
    assert transition == PRTransition.GOT_NEGATIVE


def test_check_merged_externally():
    pr_14 = FakeGHPullRequest(14)
    repo = FakeGHRepo(injected_prs=[pr_14])
    mq = MergeQueue(repo)
    mq.ask_pr(14)
    transitions = list(mq.check())
    assert len(transitions) == 0  # nothing changed so nothing should happen

    pr_14.merged = True  # PR has been merged externally
    transitions = list(mq.check())
    assert len(transitions) == 1
    pr, [(transition, params)] = transitions[0]
    assert transition == PRTransition.MERGED


def test_check_merged_by_errbot():
    pr_14 = FakeGHPullRequest(14, reviews=[FakeGHReview('user1', APPROVED)])
    repo = FakeGHRepo(injected_prs=[pr_14])
    mq = MergeQueue(repo)
    mq.ask_pr(14)
    transitions = list(mq.check())
    assert len(transitions) == 0  # nothing changed so nothing should happen

    pr_14.mergeable_state = CLEAN
    pr_14.mergeable = True
    transitions = list(mq.check())
    assert len(transitions) == 1
    pr, [(transition, params)] = transitions[0]
    assert transition == PRTransition.NOW_MERGEABLE  # PR is not blessed so nothing else should happen

    mq.bless_pr(14)
    transitions = list(mq.check())
    assert len(transitions) == 1
    assert pr_14.asked_to_be_merged
    pr, [(transition, params)] = transitions[0]
    assert transition == PRTransition.MERGING



def test_reviews():
    pr_1 = FakeGHPullRequest(1, reviews=[FakeGHReview('user1', APPROVED)], mergeable_state=CLEAN)
    repo = FakeGHRepo(injected_prs=[pr_1])
    mq = MergeQueue(repo, max_pulled_prs=2)

    mq.ask_pr(1)
    mq.bless_pr(1)

    transitions = list(mq.check())
    assert len(transitions) == 0

    pr_1.add_review(FakeGHReview('user1', COMMENTED))
    transitions = list(mq.check())
    assert len(transitions) == 0

    pr_1.add_review(FakeGHReview('user1', REQUEST_CHANGES))

    transitions = list(mq.check())
    assert len(transitions) == 1
    pr, review_transitions = transitions[0]
    assert review_transitions[0] == (PRTransition.GOT_POSITIVE, 0)
    assert review_transitions[1] == (PRTransition.GOT_NEGATIVE, 1)

def test_check_queue_depth():
    pr_14 = FakeGHPullRequest(14, reviews=[FakeGHReview('user1', APPROVED)], mergeable_state=BEHIND)
    pr_15 = FakeGHPullRequest(15, reviews=[FakeGHReview('user2', APPROVED)], mergeable_state=BEHIND)
    pr_16 = FakeGHPullRequest(16, reviews=[FakeGHReview('user2', APPROVED)], mergeable_state=BEHIND)
    repo = FakeGHRepo(injected_prs=[pr_15, pr_14, pr_16])
    mq = MergeQueue(repo, max_pulled_prs=2)
    mq.ask_pr(14)
    mq.ask_pr(15)
    mq.ask_pr(16)
    transitions = list(mq.check())
    assert len(transitions) == 0  # nothing changed so nothing should happen

    mq.bless_pr(14)
    mq.bless_pr(15)
    mq.bless_pr(16)

    # It should pull the base branch only on 14 and 15
    transitions = list(mq.check())
    assert len(transitions) == 2
    for pr, trs in transitions:
        assert trs[0][0] == PRTransition.PULLED
        assert trs[1][0] == PRTransition.PULLED_SUCCESS

    # Lets say the first one worked
    pr_14.mergeable_state = CLEAN
    pr_14.mergeable = True

    # Second time around it merge the one mergeable.
    transitions = list(mq.check())
    assert len(transitions) == 2
    for pr, trs in transitions:
        if pr.nb == 14:
            assert trs[0][0] == PRTransition.NOW_MERGEABLE and trs[1][0] == PRTransition.MERGING

    assert pr_14.asked_to_be_merged

    pr_14.merged = True  # PR has been merged
    pr_15.mergeable_state = BLOCKED  # CI still catching up

    # Third time around as a slot has been freed up, it should pull the last one.
    transitions = list(mq.check())
    assert len(transitions) == 2
    for pr, trs in transitions:
        if pr.nb == 14:
            assert trs[0][0] == PRTransition.MERGED
        elif pr.nb == 16:
            assert trs[0][0] == PRTransition.PULLED and trs[1][0] == PRTransition.PULLED_SUCCESS

    assert len(mq.pulled_prs) == 2
    pr_15.mergeable_state = DIRTY
    transitions = list(mq.check())
    assert len(transitions) == 1
    assert len(mq.pulled_prs) == 1

def test_set_stats_plugin():
    """Test setting stats plugin"""
    repo = FakeGHRepo()
    mq = MergeQueue(repo)

    assert type(mq.stats) == NoStats

    DataDogStats = getattr(importlib.import_module('datadog_stats'), 'Stats')

    mq.stats = DataDogStats(api_key="fdjkfdjkjkfd")
    assert type(mq.stats) == DataDogStats
