# THIS PROGRAM IS CONFIDENTIAL AND PROPRIETARY TO ARGO AI, LLC ("ARGO"),
# AND MAY NOT BE COPIED, REPRODUCED, MODIFIED, OR DISTRIBUTED WITHOUT
# ARGO'S PERMISSION.
# Copyright (c) 2018 Argo AI, LLC.

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
