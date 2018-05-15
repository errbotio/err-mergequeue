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

from datadog import initialize, api
from pr import PR
from stats import BaseStat


class Stats(BaseStat):
    """Stats implementation for Datadog"""

    def __init__(self, api_key: str) -> None:
        """Configure datadog api"""
        super().__init__(api_key)
        """Initialize the tracking list and datadog helper."""
        options = {
            'api_key': api_key
        }
        initialize(**options)

        self.api = api
        self.default_tags = ['argobot:merge_queue']

    def send_event(self, event_type: str, pr: PR) -> None:
        """Send event to Datadog."""
        title = f'PR-{pr.nb} - {event_type}'
        text = f'PR-{pr.nb} triggered event {event_type} after being in the queue for {pr.get_queue_time()} seconds'
        tags = [f'base_branch:{pr.base}', f'pr:{pr.nb}', f'event_type:{event_type}'] + self.default_tags

        self.api.Event.create(title=title, text=text, tags=tags)

    def send_metric(self, metric_name: str, metric_value: float, pr: PR) -> None:
        """Send metric to Datadog."""
        tags = [f'base_branch:{pr.base}', f'pr:{pr.nb}', f'metric:{metric_name}'] + self.default_tags
        self.api.Metric.send(metric=metric_name, points=metric_value, tags=tags)
