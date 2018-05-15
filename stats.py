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

"""Library for defining common stat collecting features"""
from abc import ABC, abstractmethod
from pr import PR


class BaseStat(ABC):
    """Abstract class for collecting stats."""

    def __init__(self, api_key: str) -> None:
        """Initializes the API for the stats abstraction"""
        self.api_key = api_key

    @abstractmethod
    def send_event(self, event_type: str, pr: PR) -> None:
        """Abstract method for tracking events."""
        pass

    @abstractmethod
    def send_metric(self, metric_name: str, metric_value: float, pr: PR) -> None:
        """Abstract method for tracking individual metrics."""
        pass


class NoStats(BaseStat):
    """Generic class to be used if no stat class is passed"""

    def __init__(self):
        super().__init__('')

    def send_event(self, event_type: str, pr: PR) -> None:
        """NoStats does nothing with events."""
        pass

    def send_metric(self, metric_name: str, metric_value: float, pr: PR) -> None:
        """NoStats does nothing with metrics."""
        pass
