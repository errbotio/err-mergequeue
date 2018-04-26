from threading import RLock

from importlib import import_module
from types import SimpleNamespace

from errbot import botcmd, BotPlugin, arg_botcmd
from errbot.backends.base import Identifier
from github_wrapper import Github
from mergequeue import PRTransition, MergeQueue


class Repo:
    """
    Hook to ensure backward compatibility.
    """
    def __new__(cls, name, owner, queue=None, saints=None, pulled_prs=None):
        obj = SimpleNamespace()
        obj.name = name
        obj.owner = owner
        obj.queue = queue if queue else []
        obj.saints = saints if saints else []
        obj.pulled_prs = pulled_prs if pulled_prs else []
        return obj


ROOMS = 'rooms'

# Feedback to send to chat when a PR changed state.
PR_MSG = {
    PRTransition.MERGED: '**merged**',
    PRTransition.RELEASED: 'released :open_hands:',
    PRTransition.NEW_BASE: 'Updated base of [{}]({}) to {}',
    PRTransition.NEW_BASE_ERROR: 'Error while updating the base of [{}]({}) to {}',
    PRTransition.CLOSED: '**closed**',
    PRTransition.GOT_POSITIVE: 'got a positive review ({})',
    PRTransition.GOT_NEGATIVE: 'got a negative review ({})',
    PRTransition.NO_LONGER_MERGEABLE: 'is no longer mergeable',
    PRTransition.NOW_MERGEABLE: 'is now mergeable',
    PRTransition.NEW_CHAINED_PR: 'Chained PRs:{}',
    PRTransition.MERGING: '**Merging**',
    PRTransition.PULLED: ':up:',
    PRTransition.PULLED_SUCCESS: 'up to date with its base',
    PRTransition.PULLED_FAILURE: 'pulling failed',
}

# List of feedback a user might be interesting in for his or her own PRs
USR_STATE_FEEDBACK = (
    PRTransition.MERGING,
    PRTransition.MERGED,
    PRTransition.CLOSED,
    PRTransition.GOT_POSITIVE,
    PRTransition.GOT_NEGATIVE,
    PRTransition.PULLED,
    PRTransition.PULLED_SUCCESS,
)

# List of feedback a user might be interesting in for his or her own PRs
PUBLIC_STATE_FEEDBACK = (
    PRTransition.MERGED,
    PRTransition.RELEASED,
    PRTransition.NEW_BASE,
    PRTransition.NEW_BASE_ERROR,
    PRTransition.CLOSED,
    PRTransition.GOT_POSITIVE,
    PRTransition.GOT_NEGATIVE,
    PRTransition.NEW_CHAINED_PR,
    PRTransition.MERGING,
    PRTransition.PULLED,
    PRTransition.PULLED_SUCCESS,
    PRTransition.PULLED_FAILURE,
    PRTransition.MERGED,
    PRTransition.CLOSED,
    PRTransition.GOT_POSITIVE,
    PRTransition.GOT_NEGATIVE,
    PRTransition.PULLED,
)


class Summit(BotPlugin):
    """
    This is a merge queue for Github.
    """
    def get_configuration_template(self):
        """
        Get configuration template for this plugin."""
        return {'github-token': '4efefefe4effe4efeeeef4e', }

    def activate(self):
        super(Summit, self).activate()
        if not self.config:
            # ie. if the plugin is not configured, it cannot activate.
            return

        if ROOMS not in self:
            self[ROOMS] = {}
        self.gh = Github(self.config['github-token'], api_preview=True)
        self.queues = {}  # Those are MergeQueues
        self.rooms_lock = RLock()
        self.gh_status = self.get_plugin('GHStatus')

        # Reload the state from the storage.
        with self.mutable(ROOMS) as rooms:
            for room_name, repo in rooms.items():
                for room in self[ROOMS]:
                    self.queues[room] = MergeQueue(self.gh.get_repo(repo.name), initial_queue=repo.queue)

        self.start_poller(120, method=self.check_pr_states)

    def save_queue(self, room_name: str):
        """
        Saves the state from the MergeQueues in the plugin storage.
        """
        with self.rooms_lock:
            with self.mutable(ROOMS) as rooms:
                repo = rooms[room_name]
                merge_queue = self.queues[room_name]
                repo.queue[:] = merge_queue.get_queue()
                repo.pulled_prs[:] = merge_queue.get_pulled_prs()

    @staticmethod
    def get_pr_nb(pr_nb: str) -> int:
        """
        Convert a PR number string to a PR number, allowing 101 or #101 to
        work.
        """
        return int(pr_nb.replace("#", ""))

    def check_pr_states(self):
        """
        Check the state of all PRs in all configured rooms.
        """

        usr_rev_map = {v: k for k, v in self.gh_status[self.gh_status.USERS].items()}
        with self.rooms_lock:
            with self.mutable(ROOMS) as rooms:
                for room_name, repo in rooms.items():
                    room = self.build_identifier(room_name)
                    merge_queue = self.queues[room_name]
                    for pr, new_states in merge_queue.check():
                        if not new_states:
                            continue
                        public_info = (PR_MSG[state].format(params) for state, params in new_states if state in PUBLIC_STATE_FEEDBACK)
                        public_msg = f'[#{pr.nb}]({pr.url}) {", ".join(public_info)}.'
                        self.send(room, public_msg)
                        if pr.user in usr_rev_map:
                            filtered_states = list((state, params) for state, params in new_states if state in USR_STATE_FEEDBACK)
                            if filtered_states:
                                private_info = (PR_MSG[state].format(params) for state, params in filtered_states)
                                private_msg = f'[#{pr.nb}]({pr.url}) {", ".join(private_info)}.'
                                self.send(self.build_identifier(usr_rev_map[pr.user]), private_msg)
                    self.save_queue(room_name)

    def short_pr_list(self, merge_queue: MergeQueue):
        """
        Build the short form list of PRs in a queue.
        """
        result = ''
        for i, pr in enumerate(merge_queue.get_queue()):
            mergeable = ':thumbsup:' if pr.mergeable and pr.mergeable_state == 'clean' else ':no_entry:'
            blessed = ':angel:' if pr.blessed else ''
            next_up = ':up:' if pr.nb in merge_queue.pulled_prs else ''
            result += f'{i}. [#{pr.nb}]({pr.url}) {blessed} {next_up} {pr.user} merge: {mergeable} {pr.mergeable_state}'

            dependent_prs = merge_queue.count_dependent_prs(pr)
            if dependent_prs > 0:
                result += f'{dependent_prs} Chained PRs.'
            result += '\n'
        return result

    def long_pr_list(self, merge_queue: MergeQueue, pr_list=None, level: int=0, with_desc: bool=False):
        """
        Build the long form list of PRs.
        """
        result = ''
        tab_size = 4
        indentation = ' ' * (tab_size * level)
        if pr_list is None:
            pr_list = merge_queue.get_queue()
        for i, pr in enumerate(pr_list):
            mergeable = ':thumbsup:' if pr.mergeable and pr.mergeable_state == 'clean' else ':no_entry:'
            blessed = ':angel:' if pr.blessed else ''
            next_up = ':up:' if pr.nb in merge_queue.pulled_prs else ''
            title = pr.title
            description = '\n\n'
            if with_desc:
                for line in pr.description.splitlines()[:5]:
                    description += f'    {indentation}| {line}\n\n'
            result += f'{indentation}{i+1}. [#{pr.nb}]({pr.url}) {blessed} {next_up} {pr.user} reviews: ' \
                      f'+:{pr.positive} -:{pr.negative} ~:{pr.pending} ' \
                      f'merge: {mergeable} {pr.mergeable_state} - {title}.{description}'

            if len(pr.dependents) > 0:
                result += f'{indentation}{merge_queue.count_dependent_prs(pr)} chained PRs for [#{pr.nb}]({pr.url})' \
                          f'\n\n{self.long_pr_list(merge_queue, pr.dependents, level=level + 1, with_desc=False)}'
        return result

    @botcmd
    def merge_check(self, msg, _):
        """
        Force the PR status check now.
        """
        self.check_pr_states()
        return 'Check done.'

    @botcmd(split_args_with=None)
    def merge_config(self, msg, args):
        """
        Configure the merge queue with repo for a room (defaults to the current
        room). Warning: this is killing the queue.
        """
        try:
            repo, room = self.optional_room_precheck(msg, args)
        except Exception as e:
            return f'Error {e}'

        gh_repo = self.gh.get_repo(repo)
        with self.rooms_lock:
            with self.mutable(ROOMS) as rooms:
                rooms[room] = Repo(name=repo, owner=msg.frm, queue=[],
                                   saints=[msg.frm.aclattr])
                self.queues[room] = MergeQueue(gh_repo)

        return f'Configured {room} with this repo {gh_repo.name}'

    @botcmd
    def merge_deconfig(self, msg, _):
        """
        Deconfigure the merge queue for this room. Warning: this is killing the
        queue.
        """
        if not self.config:
            return 'This plugin is not configured.'
        if not msg.is_group:
            return 'This must be done in a channel.'

        room = str(msg.frm.room)
        with self.rooms_lock:
            with self.mutable(ROOMS) as rooms:
                del rooms[room]
                del self.queues[room]
        return f'You no longer have a queue for this room {room}'

    def get_repo(self, room):
        """
        Get the specified room.
        """
        return self.gh.get_repo(self[ROOMS][room].name)

    def cmd_precheck(self, msg):
        """
        Ensure plugin state is valid for processing this command.
        """
        if not self.config:
            raise Exception('This plugin is not configured.')

        if not msg.is_group:
            raise Exception('This must be done in a channel.')

        room = str(msg.frm.room)
        if room not in self[ROOMS]:
            raise Exception('You need to link a repo to this channel with !merge config')
        return room

    @staticmethod
    def display_saints(room, saints):
        """
        Static function to display saints in a room
        """
        saint_list = '\n'.join(['Saint {0}'.format(saint) for saint in saints])
        return f'\n:orthodox_cross: Saints in {room}\n{saint_list}'

    def optional_room_precheck(self, msg, args):
        """
        Parse out a required paremeter and an optional room parameter
        (defaults to current room)
        """
        if not self.config:
            raise Exception('This plugin is not configured.')
        try:
            param1 = args[0]
        except Exception as e:
            raise Exception('Missing required parameter')
        try:
            room = args[1]
        except Exception as e:
            if not msg.is_group:
                raise Exception('Missing room parameter')
            room = str(msg.frm.room)

        return param1, room

    def is_saint(self, room: str, frm: Identifier):
        """
        Checks if a given user is a sainthood for a particular room.
        """
        with self.rooms_lock:
            return frm.aclattr in self[ROOMS][room].saints

    @botcmd(split_args_with=None)
    def merge_canonize(self, msg, args):
        """
        Give a user permission to bless PRs.
        """
        try:
            saint, room = self.optional_room_precheck(msg, args)
            saint = self.build_identifier(saint).aclattr
        except Exception as e:
            return f'Error {e}'

        if not self.is_saint(room, msg.frm):
            return f'{msg.frm} has not achieved sainthood'

        with self.mutable(ROOMS) as rooms:
            if saint not in rooms[room].saints:
                rooms[room].saints.append(saint)

        return self.display_saints(room, rooms[room].saints)

    @botcmd(split_args_with=None)
    def merge_defrock(self, msg, args):
        """
        Revoke a user's permission to bless PRs.
        """
        try:
            saint, room = self.optional_room_precheck(msg, args)
            saint = self.build_identifier(saint).aclattr
        except Exception as e:
            return f'Error {e}'

        if not self.is_saint(room, msg.frm):
            return f'{msg.frm} has not achieved sainthood'

        with self.mutable(ROOMS) as rooms:
            if saint in rooms[room].saints:
                rooms[room].saints.remove(saint)

        return self.display_saints(room, rooms[room].saints)

    @botcmd
    def merge_saints(self, msg, args):
        """
        Display the list of users who can bless PRs.
        """
        try:
            room = self.cmd_precheck(msg)
        except Exception as e:
            return str(e)

        with self.mutable(ROOMS) as rooms:
            return self.display_saints(room, rooms[room].saints)

    @arg_botcmd('merge_base_cnt', type=int)
    def merge_depth(self, msg, merge_base_cnt):
        """
        Set the number of blessed PRs to pull base on
        """

        try:
            room = self.cmd_precheck(msg)
        except Exception as e:
            return str(e)

        try:
            with self.rooms_lock:
                if not self.is_saint(room, msg.frm):
                    return f'{msg.frm} has not achieved sainthood'

                self.queues[room].max_pulled_prs = merge_base_cnt
                return f'Blessed PRs pull base count set to {merge_base_cnt}'

        except Exception as e:
            return f'Error: {e}'

    @staticmethod
    def depth_status(merge_queue):
        try:
            pulled_prs = merge_queue.pulled_prs
            count_of_merged_prs = len(pulled_prs)
            all_prs = ', '.join((str(pr_nb) for pr_nb in pulled_prs))
            return f'Blessed PRs depth set to {merge_queue.max_pulled_prs}.\n\n' + \
                   f'Current updated PR count is at {count_of_merged_prs}.\n\n' + \
                   (f'List of updated PRs: {all_prs}.' if all_prs else '')

        except Exception as e:
            return f'Error: {e}'

    @arg_botcmd('--verbose', '-v', action='store_true')
    def merge_status(self, msg, verbose: bool=False):
        """
        Return the current state of the merge queue.
        """
        try:
            room = self.cmd_precheck(msg)
        except Exception as e:
            return str(e)

        merge_queue = self.queues[room]
        yield self.long_pr_list(merge_queue, with_desc=verbose) or 'No outstanding Pull Requests in the queue.'
        if verbose:
            yield self.depth_status(merge_queue)

    @botcmd
    def merge_help(self, msg, _):
        """
        Redirect help to help plugin.
        """
        redirect_msg = msg.clone()
        redirect_msg.body = '!help {0}'.format(self.name)
        return self.get_plugin('Help').help(redirect_msg, self.name)

    def act_on_pr(self, action, msg, pr_nb, requires_sainthood=False):
        """
        Common boilerplate on acting on a PR. Action needs to be an unbounded class method on MergeQueue.
        """
        try:
            pr_nb = self.get_pr_nb(pr_nb)
        except ValueError:
            return f'Cannot convert {pr_nb} to an integer'

        try:
            room = self.cmd_precheck(msg)
        except Exception as e:
            return str(e)

        try:
            with self.rooms_lock:
                if requires_sainthood and not self.is_saint(room, msg.frm):
                    return f'{msg.frm} has not achieved sainthood'

                merge_queue = self.queues[room]
                action(merge_queue, pr_nb)
                self.save_queue(room)
                return self.short_pr_list(merge_queue)

        except Exception as e:
            return f'Error: {e}'

    @arg_botcmd('pr_nb', help='PR Number to add to the queue')
    def merge_ask(self, msg, pr_nb):
        """
        Ask for a specific PR to be merged.
        """
        return self.act_on_pr(MergeQueue.ask_pr, msg, pr_nb)

    @arg_botcmd('pr_nb', help='PR Number to remove from the queue')
    def merge_rm(self, msg, pr_nb):
        """
        Remove a specific PR from the merge queue.
        """
        return self.act_on_pr(MergeQueue.rm_pr, msg, pr_nb)

    @arg_botcmd('pr_nb', help='PR Number to bless')
    def merge_bless(self, msg, pr_nb):
        """
        Flag a PR to be automerged once it is at the front of the queue and
        ready.
        """
        return self.act_on_pr(MergeQueue.bless_pr, msg, pr_nb, requires_sainthood=True)

    @arg_botcmd('pr_nb', help='PR Number to "unbless"')
    def merge_excommunicate(self, msg, pr_nb):
        """
        Unflag a PR to be automerged.
        """
        return self.act_on_pr(MergeQueue.excommunicate_pr, msg, pr_nb, requires_sainthood=True)

    @arg_botcmd('pr_nb', help='PR Number to bump')
    def merge_bump(self, msg, pr_nb):
        """
        Bump a specific PR at the front of the queue.
        """
        return self.act_on_pr(MergeQueue.bump_pr, msg, pr_nb, requires_sainthood=True)

    @arg_botcmd('pr_nb', help='PR Number to sink')
    def merge_sink(self, msg, pr_nb):
        """
        Sink a specific PR at the bottom of the queue.
        """
        return self.act_on_pr(MergeQueue.sink_pr, msg, pr_nb, requires_sainthood=True)

    @botcmd
    def merge_list(self, msg, _):
        """
        Provides a short list of the PRs in the queue.
        """
        try:
            room = self.cmd_precheck(msg)
        except Exception as e:
            return str(e)

        with self.rooms_lock:
            return self.short_pr_list(self.queues[room])

    @arg_botcmd('api_key', help='The API key to configure the plugin ')
    @arg_botcmd('plugin', help='The plugin used to collect stats (e.g datadog)')
    def merge_statsplugin(self, msg, plugin, api_key):
        """
        Provides a short list of the PRs in the queue.
        """
        try:
            room = self.cmd_precheck(msg)
        except Exception as e:
            return str(e)

        with self.rooms_lock:
            try:
                self.queues[room].stats = getattr(import_module(f'{plugin}_stats'), 'Stats')(api_key)
                return f'{plugin} plugin configured!'
            except ModuleNotFoundError:
                return f'The {plugin} plugin does not exist'
            except AttributeError:
                return f'The {plugin} does not have a Stats class implemented'
            except Exception as e:
                return f'Unknown error {e}, while loading {plugin}'
