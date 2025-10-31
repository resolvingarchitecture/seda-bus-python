
from abc import ABC, abstractmethod
from collections import deque
import threading
import time
import sys

# Staged Event-Driven Architectural Bus supporting push-model async messaging
# and pull-model (polling). To use the push-model, register a MessageConsumer.
# To use the pull-model, use the returned MessageChannel from registering a
# channel to poll against.

class SEDABus:

    config = {}
    named_channels = {}

    callbacks = {}

    # MessageBus
    def set_config(self, config):
        self.config = config

    def register_channel(self, name):
        self.named_channels[name] = SEDAMessageChannel(self, name)

    def register_async_consumer(self, consumer):
        return

    def publish(self, message):
        return

    def publish_with_callback(self, message, client):
        return

class LifeCycle(ABC):
    @abstractmethod
    def start(self, props):
        pass

    @abstractmethod
    def pause(self):
        pass

    @abstractmethod
    def unpause(self):
        pass

    @abstractmethod
    def restart(self):
        pass

    @abstractmethod
    def shutdown(self):
        pass

    @abstractmethod
    def graceful_shutdown(self):
        pass

class MessageConsumer(ABC):
    @abstractmethod
    def receive(self, message):
        pass

class MessageProducer(ABC):
    @abstractmethod
    def send(self, message):
        pass

    @abstractmethod
    def send_with_callback(self, message, client):
        pass

    @abstractmethod
    def dead_letter(self, message):
        pass

class SEDAMessageChannel(MessageProducer, LifeCycle):

    queue = deque()

    def __init__(self, sedabus, name):
        self.sedabus = sedabus
        self.name = name

    # LifeCycle
    def start(self, props):
        return

    def pause(self):
        return

    def unpause(self):
        return

    def restart(self):
        return

    def shutdown(self):
        return

    def graceful_shutdown(self):
        return

    # MessageProducer
    def send(self, message):
        return

    def send_with_callback(self, message, client):
        return

    def dead_letter(self, message):
        return

    # SEDAMessageChannel
    def register_async_consumer(self, consumer):
        return

    def register_subscription_channel(self, channel):
        return

    def queued(self):
        return

    def get_name(self):
        return self.name