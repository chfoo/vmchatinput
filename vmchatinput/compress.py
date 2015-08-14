import datetime
import glob
import logging
import os
import re
import subprocess
import threading
import time


_logger = logging.getLogger(__name__)


class CompressThread(threading.Thread):
    def __init__(self, log_dir):
        threading.Thread.__init__(self)
        self._log_dir = log_dir

        self.daemon = True
        self._stop_event = threading.Event()
        self._running = False

    def run(self):
        self._running = True

        while self._running:
            self._compress_files()
            self._stop_event.wait(3600)

    def stop(self):
        self._running = False
        self._stop_event.set()

    def _compress_files(self):
        self._compress_log_files()
        self._compress_input_log_files()
        self._compress_images()

    def _compress_log_files(self):
        pattern = self._log_dir + '/log.*-*-*[0-9]'

        for filename in glob.iglob(pattern):
            self._compress_xz(filename)

    def _compress_input_log_files(self):
        pattern = self._log_dir + '/[0-9]*-*-*[0-9].csv'

        for filename in glob.glob(pattern):
            if self._is_file_recent(filename):
                continue

            self._compress_xz(filename)

    def _compress_images(self):
        pattern = self._log_dir + '/[0-9]*-*-*[0-9]/[0-9]*[0-9].png'

        for filename in glob.iglob(pattern):
            if self._is_file_recent(filename):
                continue

            self._compress_pngcrush(filename)

    def _is_file_recent(self, filename):
        # timestamp_ago = time.time() - 86400
        #
        # if os.path.getmtime(filename) > timestamp_ago:
        #     return True
        date_today = datetime.datetime.utcnow().date()
        file_date_str = os.path.splitext(os.path.basename(filename))[0][:10]
        date_file = datetime.datetime.strptime(file_date_str, '%Y-%m-%d').date()

        if date_file >= date_today:
            return True

        return False

    def _compress_xz(self, filename):
        _logger.info('Compressing file %s', filename)
        assert not filename.endswith('.xz')

        proc = subprocess.Popen(['xz', '-9', filename])
        proc.communicate()

        if proc.returncode != 0:
            raise Exception('xz exited abnormally: {}'.format(proc.returncode))

    def _compress_pngcrush(self, filename):
        _logger.info('Compressing image %s', filename)

        assert filename.endswith('.png')
        assert not filename.endswith('.c.png')

        new_filename = re.sub(r'\.png$', '.c.png', filename)
        proc = subprocess.Popen(['pngcrush', '-q', filename, new_filename])
        proc.communicate()

        if proc.returncode != 0:
            raise Exception('pngcrush exited abnormally: {}'
                            .format(proc.returncode))

        assert os.path.exists(new_filename)
        assert os.path.getsize(new_filename) > 0
        os.remove(filename)
