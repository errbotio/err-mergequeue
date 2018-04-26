from enum import Enum, auto
from typing import List, Tuple, Mapping
import time
from github_wrapper import PullRequest


class PR:
    """
    This is our internal representation of a PR.
    """

    def __init__(self, gh_pr: PullRequest, dependents: List['PR'] = None):
        self.nb = gh_pr.number
        self.blessed = False
        self.url = gh_pr.html_url
        self.user = gh_pr.user.login
        self.state = gh_pr.state
        self.positive = 0
        self.negative = 0
        self.pending = 0
        reviews = gh_pr.get_reviews()
        reviewers = []
        for review in reversed(list(reviews)):
            if review.user.login not in reviewers:
                if review.state != 'COMMENTED':
                    reviewers.append(review.user.login)
                    if review.state == 'APPROVED':
                        self.positive += 1
                    elif review.state in ('REQUEST_CHANGES', 'CHANGES_REQUESTED'):
                        self.negative += 1
                    elif review.state == 'PENDING' or review.state == '':
                        self.pending += 1

        self.mergeable = gh_pr.mergeable
        self.mergeable_state = gh_pr.mergeable_state
        self.title = gh_pr.title
        self.description = gh_pr.body

        self.head = gh_pr.head.ref
        self.base = gh_pr.base.ref
        self._dependents = dependents if dependents else []
        self.start_time = time.time()

    @property
    def dependents(self) -> List['PR']:
        return self._dependents

    @dependents.setter
    def dependents(self, value: List['PR']):
        self._dependents = value

    def is_ready_to_merge(self) -> bool:
        """
        Determine this PR has met the requirements to be merged.
        """
        return self.positive > 0 and self.negative < 1 and self.pending < 1 and self.mergeable and self.blessed \
               and self.mergeable_state in ('clean', 'behind')

    def __hash__(self):
        return self.nb

    def __eq__(self, other):
        if type(other) is not PR:
            return other == self.nb  # so you can find them by number
        return other.nb == self.nb

    def __str__(self):
        blessed = ':angel:' if self.blessed else ''
        return f'[#{self.nb}]({self.url}) {blessed} ({self.user})'

    def get_queue_time(self) -> float:
        """Return how long a PR has been in the queue"""
        return time.time() - self.start_time


class PRTransition(Enum):
    """
    Various transitions of states for a PR.
    """
    NEW_BASE = auto()
    NEW_BASE_ERROR = auto()
    GOT_POSITIVE = auto()
    GOT_NEGATIVE = auto()
    NO_LONGER_MERGEABLE = auto()
    NOW_MERGEABLE = auto()
    NEW_CHAINED_PR = auto()
    MERGING = auto()
    MERGED = auto()
    PULLED = auto()
    PULLED_SUCCESS = auto()
    PULLED_FAILURE = auto()
    RELEASED = auto()
    CLOSED = auto()


# This defines the feedback for a PR and the various states it went through.
PRTransitionParams = Tuple[PRTransition, Mapping[str, Tuple]]
