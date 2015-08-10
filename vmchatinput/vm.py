from __future__ import print_function

import csv
import datetime
import logging
import os
import random
import threading

from six.moves import queue
import time
import collections
import PIL.Image
import PIL.ImageMath
import six
import sys

import virtualbox
from virtualbox.library import MachineState, VBoxErrorIprtError, SessionState
from virtualbox.library_ext.keyboard import SCANCODES

_logger = logging.getLogger(__name__)


INPUT_KEYS = {
    'up': 'E_UP',
    'down': 'E_DOWN',
    'left': 'E_LEFT',
    'right': 'E_RIGHT',
    'a': 'ENTER',
    'b': 'BKSP',
    'select': 'TAB',
    'start': 'LWIN',
    '!balance': 'E_DEL',
    '!match': 'E_INS',
    '!tokens': 'ESC',
    '!song': 'ESC',
    '!slots': 'CAPS',
}
EXTRA_INPUT_KEYWORDS = {
    'balance': 'E_DEL',
    'biblethump': 'E_DEL',
    'pokemon': 'E_DEL',
    'match': 'E_INS',
    'tokens': 'ESC',
    'deilluminati': 'ESC',
    'music': 'ESC',
    'slots': 'CAPS',
    'kapow': 'CAPS',
    'entei': ['f', 'ALT'],
    'chatot': ['s', 'CTRL'],
    'blaziken': ['F4', 'ALT'],
}
KAPOW_KEYS = [
    '!kapow',
    '!fissure',
    '!sheercold', '!sheer',
    '!guillotine',
    '!horndrill', '!horn',
    '!explosion',
    '!selfdestruct', '!self',
]
LEFT_BUTTON = 0x01
RIGHT_BUTTON = 0x02
MIDDLE_BUTTON = 0x04

MAX_MOUSE_MOVE_AMOUNT = 64

LEFT_CLICK_WORDS = frozenset([
    'a', 'an', 'the', 'this', 'and', 'i',
])
RIGHT_CLICK_WORDS = frozenset([
    '***', 'wow', 'streamer', 'naughty',
])
CURSOR_MOVE_WORDS = frozenset([
    'kappa', 'trihard', 'wutface', 'onehand', 'dansgame', 'failfish',
    'brokeback', 'residentsleeper',
])
RESET_WORDS = frozenset([
    '/me', 'non-whitelisted', 'excessive',
])


class VMThread(threading.Thread):
    def __init__(self, message_queue, machine_name, log_dir):
        threading.Thread.__init__(self)
        self._message_queue = message_queue
        self._machine_name = machine_name
        self._log_dir = log_dir
        self._running = False
        self.daemon = True
        self._vbox = None
        self._vbox_machine = None
        self._vbox_session = None
        self._logging = InputLogging(log_dir)
        self._input_counter = 0
        self._prev_button_flags = 0
        self._frozen_checker = FrozenChecker()

    def run(self):
        _logger.info('Starting VM client.')

        self._running = True

        self._setup_virtualbox()

        while self._running:
            try:
                nick, message = self._message_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if not self._start_machine_if_needed():
                continue

            try:
                self._process_input(nick, message)
            except (ValueError, KeyError, TypeError, IndexError):
                _logger.exception('Error processing input')

        _logger.info('Stopped VM client.')

    def stop(self):
        _logger.info('Stopping VM client.')
        self._running = False

    def _setup_virtualbox(self):
        self._vbox = virtualbox.VirtualBox()
        self._vbox_machine = self._vbox.find_machine(self._machine_name)

    def _start_machine_if_needed(self):
        if self._vbox_machine.state in (MachineState.powered_off,
                                        MachineState.saved,
                                        MachineState.aborted):
            if self._vbox_session and \
                    self._vbox_session.state == SessionState.locked:
                _logger.info('Waiting for existing session to unlock.')
                self._vbox_session.unlock_machine()
                self._vbox_session = None
                time.sleep(5)

            _logger.info('Starting machine.')
            self._vbox_session = virtualbox.Session()
            progress = self._vbox_machine.launch_vm_process(self._vbox_session)
            progress.wait_for_completion()
            return False
        elif self._vbox_machine.state == MachineState.stuck:
            _logger.warning('Machine is stuck.')
            self._vbox_session.console.power_down()
            time.sleep(5)
        elif self._vbox_machine.state != MachineState.running:
            _logger.info('Waiting for machine. Current: %s',
                          self._vbox_machine.state)
            time.sleep(5)
            return False
        else:
            if not self._vbox_session:
                self._vbox_session = self._vbox_machine.create_session()

            return True

    def _process_input(self, nick, message):
        nick = nick.lower()
        message = message.strip()
        words = message.split()
        lowered_words = list([word.lower() for word in words])
        lowered_words_set = frozenset(lowered_words)

        if not words:
            return

        first_word = lowered_words[0]

        if first_word == '!move' and len(words) >= 2:
            first_word = '!' + words[1]

        if first_word in INPUT_KEYS:
            key = INPUT_KEYS[first_word]
            self._logging.write_log(nick, key)
            self._send_key(key)

        elif frozenset(EXTRA_INPUT_KEYWORDS.keys()) & lowered_words_set:
            matches = frozenset(EXTRA_INPUT_KEYWORDS.keys()) \
                & frozenset(lowered_words)
            matches = list(matches)
            matches.sort()
            key = EXTRA_INPUT_KEYWORDS[matches[0]]

            if isinstance(key, list):
                key, modifier = key

                self._logging.write_log(nick, '{}+{}'.format(key, modifier))
                self._send_key(modifier, down=True, up=False)
                self._send_key(key)
                self._send_key(modifier, down=False, up=True)
            else:
                self._logging.write_log(nick, key)
                self._send_key(key)

        elif first_word in KAPOW_KEYS:
            self._logging.write_log(nick, 'CAD')
            self._send_cad()

        elif first_word.startswith('@'):
            self._send_key('ALT', down=True, up=False)

            num = min(10, len(first_word) - 1)

            self._logging.write_log(nick, 'AltTab:{}'.format(num))

            for dummy in range(num):
                self._send_key('TAB')

            self._send_key('ALT', down=False, up=True)

        elif first_word == '!a' or LEFT_CLICK_WORDS & lowered_words_set:
            self._logging.write_log(nick, 'LClick')
            self._send_click(LEFT_BUTTON)

        elif first_word == '!b' or RIGHT_CLICK_WORDS & lowered_words_set:
            self._logging.write_log(nick, 'RClick')
            self._send_click(RIGHT_BUTTON)

        elif first_word == '!c':
            self._logging.write_log(nick, 'LMBDown')
            self._send_mouse_down(LEFT_BUTTON)

        elif first_word == '!d':
            self._logging.write_log(nick, 'MBUp')
            self._send_mouse_up()

        elif first_word in '!-' or CURSOR_MOVE_WORDS & lowered_words_set:
            delta = random_value(len(nick)) % (MAX_MOUSE_MOVE_AMOUNT * 2) \
                - MAX_MOUSE_MOVE_AMOUNT

            if delta == 0 or (
                    len(nick) % 4 == 0 and
                    abs(delta) < MAX_MOUSE_MOVE_AMOUNT / 3):
                self._logging.write_log(nick, 'CenterXY')
                self._center_mouse()
            elif len(nick) % 2 == 0:
                self._logging.write_log(nick, 'XD:{}'.format(delta))
                self._move_mouse(delta, 0)
            else:
                self._logging.write_log(nick, 'YD:{}'.format(delta))
                self._move_mouse(0, delta)

        elif first_word == '!bet':
            if len(words) < 3:
                return

            try:
                bet_amount = int(words[1])
            except ValueError:
                return

            bet_team = words[2]

            delta = random_value(bet_amount * len(nick)) % \
                (MAX_MOUSE_MOVE_AMOUNT * 2) - MAX_MOUSE_MOVE_AMOUNT

            if bet_team == 'blue':
                self._logging.write_log(nick, 'XD:{}'.format(delta))
                self._move_mouse(delta, 0)
            elif bet_team == 'red':
                self._logging.write_log(nick, 'YD:{}'.format(delta))
                self._move_mouse(0, delta)

        elif RESET_WORDS & lowered_words_set and \
                self._input_counter % len(RESET_WORDS) == 0:
            self._logging.write_log(nick, 'Reset')
            self._reset_machine()

        if first_word not in INPUT_KEYS:
            word = random.choice(words)[:32]
            try:
                word.encode('ascii')
            except UnicodeError:
                pass
            else:
                self._logging.write_log(nick, 'Word:{}'.format(word))
                self._send_keys(word)
                self._send_keys(' ')

        self._input_counter += 1

        if self._input_counter % 100 == 0 or self._input_counter == 5:
            try:
                image_data = self._screenshot()
            except VBoxErrorIprtError:
                _logger.exception('Screenshot error')
                self._frozen_checker.increment_screenshot_error()
            else:
                self._frozen_checker.add_image(image_data)

            if self._frozen_checker.is_frozen():
                _logger.warning('Machine appears frozen')
                self._reset_machine()

    def _send_keys(self, keys_string):
        for key_string in keys_string:
            self._send_key(key_string)

    def _send_key(self, key_string, down=True, up=True):
        if key_string not in SCANCODES:
            _logger.debug('Ignored a key')
            return

        _logger.debug('Send key %s', key_string)

        presses, releases = SCANCODES[key_string]

        if down:
            self._vbox_session.console.keyboard.put_scancodes(presses)
            time.sleep(0.001)

        if up:
            self._vbox_session.console.keyboard.put_scancodes(releases)
            time.sleep(0.001)

    def _send_click(self, button):
        self._send_mouse_down(button)
        time.sleep(0.001)
        self._send_mouse_up()

    def _send_mouse_down(self, button):
        _logger.debug('Send button down %s', button)
        self._vbox_session.console.mouse.put_mouse_event(0, 0, 0, 0, button)
        self._prev_button_flags = button

    def _send_mouse_up(self):
        _logger.debug('Send button up')
        self._vbox_session.console.mouse.put_mouse_event(0, 0, 0, 0, 0)
        self._prev_button_flags = 0

    def _move_mouse(self, x, y, increment=10):
        _logger.debug('Request button move %d %d', x, y)
        accel_multiplier = 0.95
        multiplier_x = -1 if x < 0 else 1
        multiplier_y = -1 if y < 0 else 1
        remain_x = abs(x)
        remain_y = abs(y)

        for dummy in range(1000):
            this_x = 0
            this_y = 0

            if remain_x > 0:
                this_x = min(remain_x, increment)
                remain_x -= this_x
                remain_x = int(remain_x * accel_multiplier)

            if remain_y > 0:
                this_y = min(remain_y, increment)
                remain_y -= increment
                remain_y = int(remain_y * accel_multiplier)

            send_x = this_x * multiplier_x
            send_y = this_y * multiplier_y
            _logger.debug('Send button move %d %d', send_x, send_y)

            self._vbox_session.console.mouse.put_mouse_event(
                send_x, send_y, 0, 0, self._prev_button_flags)

            time.sleep(0.1)

            if remain_x <= 0 and remain_y <= 0:
                break

    def _center_mouse(self):
        _logger.debug('Center mouse')
        width, height, _, _, _ = self._vbox_session.console.display \
            .get_screen_resolution(0)

        self._move_mouse(-width, -height)
        self._move_mouse(width // 2, height // 2)

    def _send_cad(self):
        _logger.debug('Send CTRL+ALT+DEL')
        self._vbox_session.console.keyboard.put_cad()

    def _screenshot(self):
        width, height, _, _, _ = self._vbox_session.console.display\
            .get_screen_resolution(0)
        data = self._vbox_session.console.display\
            .take_screen_shot_png_to_array(0, width, height)
        self._logging.save_screenshot(data)

        return data

    def _reset_machine(self):
        _logger.debug('Reset machine')
        self._vbox_session.console.reset()


class InputLogging(object):
    def __init__(self, log_dir):
        self._log_dir = log_dir
        self._current_date = None
        self._log_file = None
        self._log_writer = None

    def save_screenshot(self, data):
        with open(self._get_screenshot_path(), 'wb') as file:
            file.write(data)

    def _get_screenshot_path(self):
        datetime_now = datetime.datetime.utcnow()
        date_str = datetime_now.date().isoformat()
        datetime_str = datetime_now.isoformat()

        dir_path = os.path.join(self._log_dir, date_str)
        file_path = os.path.join(dir_path, datetime_str + '.png')

        if not os.path.exists(dir_path):
            os.mkdir(dir_path)

        return file_path

    def write_log(self, nick, value):
        datetime_now = datetime.datetime.utcnow()
        date_now = datetime_now.date()

        if self._current_date != date_now:
            if self._log_file:
                self._log_file.close()

            self._open_log_file()
            self._current_date = date_now

        self._log_writer.writerow([datetime_now.isoformat(), nick, value])

        print('>', nick, value, file=sys.stderr)

    def _open_log_file(self):
        date_str = datetime.datetime.utcnow().date().isoformat()
        path = os.path.join(self._log_dir, date_str + '.csv')
        self._log_file = open(path, 'a')
        self._log_writer = csv.writer(self._log_file)


class FrozenChecker(object):
    def __init__(self):
        self._images = collections.deque((), 3)
        self._screenshot_error_count = 0

    def add_image(self, image_data):
        self._screenshot_error_count = 0
        image = PIL.Image.open(six.BytesIO(image_data)).convert('L')
        self._images.append(image)

    def is_frozen(self):
        if self._screenshot_error_count > 3:
            return True

        num_images = len(self._images)

        if num_images < 2:
            return False

        results = []

        for index in range(num_images - 1):
            results.append(
                self._is_image_equal(self._images[index],
                                     self._images[index + 1])
            )

        _logger.debug('Frozen check %s', results)

        return all(results)

    def increment_screenshot_error(self):
        self._screenshot_error_count += 1

    def _is_image_equal(self, image1, image2):
        result_image = PIL.ImageMath.eval('abs(a - b)', a=image1, b=image2)

        return not result_image.getbbox()


def random_value(seed_num):
    mask = (1 << 30) - 1
    result = (1103515245 * seed_num + 12345) % 2147483648
    result &= mask
    return result
