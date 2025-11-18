
from abc import ABC, abstractmethod
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import os
import threading
import time
import sys


# Staged Event-Driven Architectural Bus supporting push-model async messaging
# and pull-model (polling). To use the push-model, register a MessageConsumer.
# To use the pull-model, use the returned MessageChannel from registering a
# channel to poll against.

class LifeCycle(ABC):
    @abstractmethod
    def start(self):
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
    def dead_letter(self, message):
        pass

class SEDAMessageChannel(MessageProducer, LifeCycle):

    accepting = False
    flush = False
    round_robin = 0
    queue = deque()
    consumers: list[MessageConsumer] = []

    def __init__(self, bus, name, config):
        self.bus = bus
        self.name = name
        self.config = config

    # LifeCycle
    def start(self):
        self.accepting = True
        return

    def pause(self):
        self.accepting = False
        return

    def unpause(self):
        self.accepting = True
        return

    def restart(self):
        self.shutdown()
        self.start()
        return

    def shutdown(self):
        self.accepting = False
        return

    def graceful_shutdown(self):
        self.accepting = False
        return

    # SEDAMessageChannel
    def get_name(self):
        return self.name

    def queued(self):
        return self.queue.count(self)

    def register_async_consumer(self, consumer):
        self.consumers.append(consumer)
        return

    def ack(self, message):
        self.queue.remove(message)

    # MessageProducer
    # Queue message for sending
    def send(self, message):
        if self.accepting:
            self.queue.append(message)

    def dead_letter(self, message):
        # TODO: persist dead message
        return

    def process(self, message):
        if self.consumers.count(self) > 0:
            if self.round_robin == self.consumers.count(self):
                self.round_robin = 0
            c = self.consumers.pop(self.round_robin)
            self.round_robin += 1
            c.receive(message)
            self.ack(message)

    # Receive message from channel with blocking.
    # Process all registered async Message Consumers if present.
    # Return message in case called by polling Message Consumer.
    def receive(self):
        message = self.queue.popleft()
        self.process(message)
        self.bus.completed(message)
        return message

    def set_flush(self, flush):
        self.flush = flush

    def get_flush(self):
        return self.flush

    def clear_unprocessed(self):
        # TODO: delete unprocessed persisted messages
        pass

    def send_unprocessed(self):
        # TODO: send unprocessed persisted messages
        pass

class WorkerThreadPool(threading.Thread):

    running = False
    channels: list[SEDAMessageChannel] = []

    def __init__(self, max_workers):
        super().__init__()
        self.pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="SBW-")

    def run(self):
        running = True
        while running:
            time.sleep(0.1)
            for c in self.channels:
                if c.get_flush():
                    while c.queued() > 0:
                        self.pool.submit(c.receive())
                    c.set_flush(False)
                elif c.queued() > 0:
                    self.pool.submit(c.receive())

    def shutdown(self):
        self.running = False
        self.pool.shutdown(wait=True)

class SEDABus(LifeCycle):

    pool = WorkerThreadPool(max_workers=5)
    named_channels = {}
    callbacks = {}

    def __init__(self, config):
        print("SEDA Bus initializing...")
        self.config = config

    # LifeCycle
    def start(self):
        print("SEDA Bus starting...")
        return

    def pause(self):
        return

    def unpause(self):
        return

    def restart(self):
        return

    def shutdown(self):
        print("SEDA Bus stopping...")
        return

    def graceful_shutdown(self):
        return

    # SEDA Bus
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

    def completed(self, message):
        return

    def clear_unprocessed(self):
        return

    def resume_unprocessed(self):
        return


if __name__ == "__main__":
    print("Welcome to SEDA Bus...")
    gil_disabled = getattr(sys, '_is_gil_enabled', False)
    print("GIL disabled:", gil_disabled)
    if not gil_disabled:
        print("Gil enabled - SEDA Bus can not work so exiting.")
        sys.exit(1)
    print("Number of CPU cores:", os.cpu_count())
    config = {}
    sedabus = SEDABus(config)
    sedabus.start()
    running = True
    i = 0
    while running:
        print(".")
        time.sleep(1)
        i+=1
        if i > 10:
            print("Reached 10 seconds, shutting down...")
            sedabus.shutdown()
            print("Exiting...")
            sys.exit()
