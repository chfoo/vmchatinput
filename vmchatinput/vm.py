from __future__ import print_function

import logging
import re
import subprocess
import threading

from six.moves import queue
import time
import collections
import PIL.Image
import PIL.ImageMath
import six

import virtualbox
from virtualbox.library import MachineState, VBoxErrorIprtError, SessionState
from vmchatinput.input import ChatInput

_logger = logging.getLogger(__name__)


class VMThread(threading.Thread):
    def __init__(self, message_queue, machine_name, log_dir,
                 minimized_gui=False):
        threading.Thread.__init__(self)
        self._message_queue = message_queue
        self._machine_name = machine_name
        self._log_dir = log_dir
        self._minimized_gui = minimized_gui
        self._running = False
        self.daemon = True
        self._vbox = None
        self._vbox_machine = None
        self._vbox_session = None
        self._chat_input = ChatInput(log_dir)
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

            if self._minimized_gui:
                self._minimize_vm_window()

            return False
        else:
            if not self._vbox_session:
                self._vbox_session = self._vbox_machine.create_session()

            if self._vbox_machine.state == MachineState.stuck:
                _logger.warning('Machine is stuck.')
                self._vbox_session.console.power_down()
                time.sleep(5)
                return False
            elif self._vbox_machine.state != MachineState.running:
                _logger.info('Waiting for machine. Current: %s',
                              self._vbox_machine.state)
                time.sleep(5)
                return False
            else:
                return True

    def _process_input(self, nick, message):
        self._chat_input.process_input(nick, message,
                                       self._vbox_session.console)
        input_count = self._chat_input.input_counter

        if input_count % 100 == 0 or input_count == 5:
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

    def _screenshot(self):
        width, height, _, _, _ = self._vbox_session.console.display\
            .get_screen_resolution(0)
        data = self._vbox_session.console.display\
            .take_screen_shot_png_to_array(0, width, height)
        self._chat_input.input_logger.save_screenshot(data)

        return data

    def _reset_machine(self):
        _logger.debug('Reset machine')
        self._vbox_session.console.reset()

    def _minimize_vm_window(self):
        try:
            proc = subprocess.Popen(['wmctrl', '-l'], stdout=subprocess.PIPE)
        except OSError:
            return

        stdout_data = proc.communicate()[0].decode('utf-8', 'replace')

        match = re.search(
            r'^0x([a-f0-9]+) +\w+ +\S+ +{} +.* - Oracle VM VirtualBox$'
            .format(re.escape(self._machine_name)),
            stdout_data,
            re.MULTILINE
        )

        if match:
            proc = subprocess.Popen([
                'xdotool', 'windowminimize', '0x{}'.format(match.group(1)),
            ])
            proc.communicate()


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
