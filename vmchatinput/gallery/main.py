import logging
import threading
from vmchatinput.gallery.render import Renderer

_logger = logging.getLogger(__name__)


class GalleryThread(threading.Thread):
    def __init__(self, log_dir, output_dir):
        threading.Thread.__init__(self)
        self._log_dir = log_dir

        self.daemon = True
        self._stop_event = threading.Event()
        self._running = False

        self._renderer = Renderer(log_dir, output_dir)

    def run(self):
        self._running = True

        while self._running:
            self._renderer.render()
            return
            self._stop_event.wait(3600 * 12)

    def stop(self):
        self._running = False
        self._stop_event.set()
