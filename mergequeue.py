from pr import PR, PRTransition, PRTransitionParams
from typing import List, Tuple, Any, Generator, Union
from stats import BaseStat, NoStats
import logging

log = logging.getLogger(__name__)

MAX_PULLED_PR = 3


class MergeQueueException(Exception):
    pass


class MergeQueue:
    def __init__(self,
                 gh_repo, 
                 max_pulled_prs: int = MAX_PULLED_PR,
                 initial_queue: List[PR] = None,
                 stats: BaseStat=None,
                 initial_pulled_prs: List[int] = None):
        self.max_pulled_prs = max_pulled_prs
        self.gh_repo = gh_repo
        self.queue = initial_queue if initial_queue else []
        self.pulled_prs = initial_pulled_prs if initial_pulled_prs else []
        self.stats = stats or NoStats()

    def get_queue(self) -> List[PR]:
        """
        Used to save the state.
        :return: the current state of the queue
        """
        return self.queue

    def get_pulled_prs(self) -> List[int]:
        """
        Used to save the state.
        :return: the current state of the PRs being pulled.
        """
        return self.pulled_prs

    def get_pr(self, pr_nb: int) -> Tuple[Union[PR], Union[Any]]:
        """
        Get PR from the repo.
        """
        try:
            gh_pr = self.gh_repo.get_pull(pr_nb)
            return PR(gh_pr), gh_pr
        except Exception:
            raise MergeQueueException('Could not find this PR.')

    def ask_pr(self, pr_nb: int):
        if pr_nb in self.queue:
            raise MergeQueueException('This PR is already in the queue.')

        pr, _ = self.get_pr(pr_nb)
        if pr.state == 'closed':
            raise MergeQueueException('This PR is already closed.')

        self.queue.append(pr)
        self.stats.send_event('added', pr)

    def rm_pr(self, pr_nb: Union[int, PR]):
        if pr_nb not in self.queue:
            raise MergeQueueException('This PR is not on this queue.')

        pr = self.queue.remove(pr_nb)
        if pr_nb in self.pulled_prs:
            self.pulled_prs.remove(pr_nb)

        self.stats.send_event('removed', pr)

    def bless_pr(self, pr_nb: Union[int, PR]):
        if pr_nb not in self.queue:
            raise MergeQueueException('This PR is not on this queue.')

        index = self.queue.index(pr_nb)
        pr = self.queue[index]
        pr.blessed = True
        self.stats.send_event('blessed', pr)
        self.stats.send_metric('queue_time_to_bless', pr.get_queue_time(), pr)

    def bump_pr(self, pr_nb: Union[int, PR]):
        if pr_nb not in self.queue:
            raise MergeQueueException('This PR is not on this queue.')

        index = self.queue.index(pr_nb)
        if not self.queue[index].blessed:
            raise MergeQueueException('Only a blessed :angel: PR can ascend to the front of the queue')

        self.queue.insert(0, self.queue.pop(index))

        if pr_nb in self.pulled_prs:
            self.pulled_prs.insert(0, self.pulled_prs.pop(self.pulled_prs.index(pr_nb)))
        else:
            if len(self.pulled_prs) >= self.max_pulled_prs:
                self.remove_pulled_pr(self.pulled_prs[-1])
            self.pulled_prs.insert(0, pr_nb)

    def sink_pr(self, pr_nb: Union[int, PR]):
        if pr_nb not in self.queue:
            raise MergeQueueException('This PR is not on this queue.')

        self.queue.append(self.queue.pop(self.queue.index(pr_nb)))

    def excommunicate_pr(self, pr_nb: Union[int, PR]):
        if pr_nb not in self.queue:
            raise MergeQueueException('This PR is not on this queue.')

        index = self.queue.index(pr_nb)
        pr = self.queue[index]
        pr.blessed = False
        self.stats.send_event('excommunicated', pr)
        if pr_nb in self.pulled_prs:
            self.pulled_prs.remove(pr_nb)

    def get_pending_statuses(self, pr: PR) -> List:
        """
        Return the pending required status checks for its base
        branch.
        """
        requirements = list(self.gh_repo.get_branch(pr.base).contexts)
        for status in self.gh_repo.get_commit(pr.head).get_statuses():
            if status.context in requirements and status.state != 'pending':
                requirements.remove(status.context)
        return requirements

    def check_required_statuses(self, pr: PR) -> bool:
        """
        Return if a PR has met all the required status checks for its base
        branch.
        """
        requirements = list(self.gh_repo.get_branch(pr.base).contexts)
        for status in self.gh_repo.get_commit(pr.head).get_statuses():
            if status.context in requirements and status.state == 'success':
                requirements.remove(status.context)

        return len(requirements) < 1

    def get_dependents_prs(self, pr: PR) -> List[PR]:
        """
        Return a list of dependent PRs.
        """
        dependents = []
        for dependent_pr in self.gh_repo.get_pulls(base=pr.head):
            element = [existing_pr for existing_pr in self.queue if
                       existing_pr.nb == dependent_pr.number]
            if len(element) > 0:
                dependents.append(element[0])
            else:
                new_pr = PR(dependent_pr)
                new_pr.dependents = self.get_dependents_prs(new_pr)
                dependents.append(new_pr)
        return dependents

    def count_dependent_prs(self, pr: PR) -> int:
        """
        Recursively count the number of dependent PRs.
        """
        count = 0
        for dependents in pr.dependents:
            count += 1 + self.count_dependent_prs(dependents)
        return count

    def remove_pulled_pr(self, pr_nb: int) -> bool:
        if pr_nb not in self.pulled_prs:
            return False
        self.pulled_prs.remove(pr_nb)
        return True

    def check(self) -> Generator[Tuple[PR, List[PRTransitionParams]], None, None]:
        new_queue = []
        already_merging_a_pr = False

        for idx, old_pr in enumerate(self.queue):
            log.debug('Checking pr %s...', old_pr.nb)
            new_pr, gh_pr = self.get_pr(old_pr.nb)
            if not new_pr:  # it errored
                continue
            new_states = []
            new_pr.dependents = self.get_dependents_prs(new_pr)
            if gh_pr.merged:
                new_states.append((PRTransition.MERGED, None))
                if self.remove_pulled_pr(old_pr.nb):
                    new_states.append((PRTransition.RELEASED, None))

                for dependent in new_pr.dependents:
                    _, dependent_gh_pr = self.get_pr(dependent.nb)
                    if not _:  # it errored
                        continue

                    try:
                        dependent_gh_pr.edit(base=new_pr.base)
                        new_states.append((PRTransition.NEW_BASE, (dependent.nb, dependent.url, new_pr.base)))
                    except Exception:
                        new_states.append((PRTransition.NEW_BASE_ERROR, (dependent.nb, dependent.url, new_pr.base)))

                #  Automatically delete the branch that has been merged and after the children have been updated.
                try:
                    self.gh_repo.get_git_ref(f'heads/{gh_pr.head.ref}').delete()
                except:
                    log.exception('Could not remote a dangling PR branch.')
            elif new_pr.state != 'open':
                new_states.append((PRTransition.CLOSED, None))
                if self.remove_pulled_pr(new_pr.nb):
                    new_states.append((PRTransition.RELEASED, None))

            else:
                # forward the state
                new_pr.blessed = old_pr.blessed
                new_pr.start_time = old_pr.start_time
                if new_pr.mergeable_state == 'unknown':
                    # Keep the last known state: if it comes back
                    # to the same state we don't spam the chat.
                    new_pr.mergeable_state = old_pr.mergeable_state
                elif new_pr.mergeable_state == 'unstable':
                    # The GH will mark  a PR as unstable if a
                    # non-required status check has not passed
                    new_pr.mergeable_state = 'clean' if self.check_required_statuses(new_pr) else new_pr.mergeable_state
                elif new_pr.mergeable_state == 'dirty':
                    #Dirty PR signify merge conflicts and will back up the pull queue
                    self.remove_pulled_pr(new_pr.nb)

                new_queue.append(new_pr)
                if old_pr.positive != new_pr.positive:
                    new_states.append((PRTransition.GOT_POSITIVE, new_pr.positive))
                if old_pr.negative != new_pr.negative:
                    new_states.append((PRTransition.GOT_NEGATIVE, new_pr.negative))
                if old_pr.mergeable and not new_pr.mergeable:
                    new_states.append((PRTransition.NO_LONGER_MERGEABLE, None))
                if not old_pr.mergeable and new_pr.mergeable:
                    new_states.append((PRTransition.NOW_MERGEABLE, None))
                if self.count_dependent_prs(old_pr) != self.count_dependent_prs(new_pr):
                    new_states.append((PRTransition.NEW_CHAINED_PR, self.count_dependent_prs(new_pr)))

                if not already_merging_a_pr and new_pr.mergeable_state == 'clean' and new_pr.is_ready_to_merge():
                    new_states.append((PRTransition.MERGING, None))
                    gh_pr.merge(commit_title='Merged automatically by argobot.')
                    self.stats.send_event('merged', new_pr)
                    self.stats.send_metric('queue_time_to_merge', new_pr.get_queue_time(), new_pr)
                    already_merging_a_pr = True
                elif new_pr.blessed and new_pr.mergeable_state == 'behind':
                    if new_pr.nb not in self.pulled_prs and len(self.pulled_prs) < self.max_pulled_prs:
                        self.pulled_prs.append(new_pr.nb)
                        new_states.append((PRTransition.PULLED, None))
                    # pull the base of the PR into the PR.
                    if new_pr.nb in self.pulled_prs:
                        if self.gh_repo.merge(base=gh_pr.head.ref, head=gh_pr.base.ref):
                            new_states.append((PRTransition.PULLED_SUCCESS, None))
                        else:
                            new_states.append((PRTransition.PULLED_FAILURE, None))
            if new_states:
                yield new_pr, new_states
        self.queue = new_queue
