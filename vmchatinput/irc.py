from __future__ import absolute_import

import logging
import random
import threading
import irc.client

from six.moves import queue


_logger = logging.getLogger(__name__)


irc.client.ServerConnection.buffer_class.errors = 'replace'


MIN_RECONNECT_TIME = 60
MAX_RECONNECT_TIME = 60 * 60


assert MIN_RECONNECT_TIME < MAX_RECONNECT_TIME


class Client(irc.client.SimpleIRCClient):

    def __init__(self, channel, message_queue):
        irc.client.SimpleIRCClient.__init__(self)
        self._channel = channel
        self._message_queue = message_queue
        self.connection.buffer_class.errors = 'replace'
        self._reconnect_time = MIN_RECONNECT_TIME
        self._connect_args = None

    def connect(self, *args, **kwargs):
        _logger.info('Connecting to server %s', args)
        self._connect_args = (args, kwargs)
        irc.client.SimpleIRCClient.connect(self, *args, **kwargs)

    def stop_autoconnect(self):
        self._connect_args = None

    def on_welcome(self, connection, event):
        self._reconnect_time = MIN_RECONNECT_TIME
        _logger.info('Joining channel %s', self._channel)
        connection.join(self._channel)

    def on_disconnect(self, connection, event):
        _logger.info('Disconnected!')

        if self._connect_args:
            _logger.info('Reconnecting in %d seconds...', self._reconnect_time)
            self.connection.execute_delayed(self._reconnect_time,
                                            self._reconnect)

    def _reconnect(self):
        if self.connection.is_connected() or not self._connect_args:
            return

        _logger.info('Reconnecting...')

        try:
            self.connect(*self._connect_args[0], **self._connect_args[1])
        except irc.client.ServerConnectionError:
            _logger.exception('Failed to reconnect.')
            self._reconnect_time *= 2
            self._reconnect_time = min(MAX_RECONNECT_TIME, self._reconnect_time)
            _logger.info('Reconnecting in %d seconds...', self._reconnect_time)
            self.connection.execute_delayed(self._reconnect_time,
                                            self._reconnect)

    def on_pubmsg(self, connection, event):
        if not event.target == self._channel:
            return

        if not hasattr(event.source, 'nick'):
            return

        nick = event.source.nick
        message = event.arguments[0]

        if message.startswith('\x01ACTION'):
            message = message[7:-1]

        _logger.debug('Put message %s %s', nick, message)

        try:
            self._message_queue.put_nowait((nick, message))
        except queue.Full:
            pass


class IRCThread(threading.Thread):
    def __init__(self, message_queue, channel, irc_host, irc_port=6667):
        threading.Thread.__init__(self)
        self._message_queue = message_queue
        self._channel = channel
        self._irc_host = irc_host
        self._irc_port = irc_port
        self._running = False
        self.daemon = True

    def run(self):
        _logger.info('Starting IRC client.')

        self._running = True
        client = Client(self._channel, self._message_queue)
        client.connect(self._irc_host, self._irc_port, self.get_nickname())

        while self._running:
            client.reactor.process_once(0.2)

        client.stop_autoconnect()
        client.reactor.disconnect_all()

        _logger.info('Stopped IRC client.')

    def stop(self):
        _logger.info('Stopping IRC client.')
        self._running = False

    def get_nickname(self):
        return 'justinfan{}'.format(random.randint(1000, 1000000))
