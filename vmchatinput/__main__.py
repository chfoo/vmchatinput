import json
import logging
import atexit
from logging.handlers import TimedRotatingFileHandler
import os

from six.moves import queue
import argparse
import signal
import sys
from vmchatinput.compress import CompressThread

from vmchatinput.irc import IRCThread
from vmchatinput.vm import VMThread

_logger = logging.getLogger(__name__)


def main():
    message_queue = queue.Queue(10)
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('config_file')
    args = arg_parser.parse_args()

    with open(args.config_file) as file:
        config = json.load(file)

    if config.get('debug'):
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(levelname)s %(message)s'))

    log_handler = TimedRotatingFileHandler(
        os.path.join(config['log_dir'], 'log'),
        utc=True, when='midnight',
    )
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    log_handler.setFormatter(formatter)

    console_handler.setLevel(log_level)
    log_handler.setLevel(log_level)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(log_handler)

    irc_thread = IRCThread(message_queue, config['channel'], config['server'])
    vm_thread = VMThread(message_queue, config['virtual_machine'],
                         config['log_dir'], config.get('minimized_gui'))
    compress_thread = CompressThread(config['log_dir'])

    threads = [irc_thread, vm_thread, compress_thread]
    non_local_dict = {'running': True}

    for thread in threads:
        thread.start()

    @atexit.register
    def cleanup():
        if non_local_dict['running']:
            non_local_dict['running'] = False
            for thread in threads:
                _logger.info('Stopping thread %s', thread)
                thread.stop()
                thread.join(1)

            _logger.info('Threads stopped.')

    def stop(dummy1, dummy2):
        cleanup()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    while non_local_dict['running']:
        for thread in threads:
            thread.join(timeout=1)

            if not thread.is_alive() and non_local_dict['running']:
                raise Exception('A thread died: {}'.format(thread))

    _logger.info('Quiting.')


if __name__ == '__main__':
    main()
