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
