#!/usr/bin/env python2
from __future__ import print_function

import subprocess
import sys
import time
import atexit


if __name__ == '__main__':
    MIN_SLEEP_TIME = 60
    MAX_SLEEP_TIME = 60 * 60

    assert MIN_SLEEP_TIME < MAX_SLEEP_TIME

    sleep_time = MIN_SLEEP_TIME
    proc = None

    @atexit.register
    def cleanup():
        if not proc:
            return

        print('Cleaning up...')

        for dummy in range(50):
            proc.poll()
            if proc.returncode is None:
                try:
                    proc.terminate()
                except OSError:
                    pass

                time.sleep(0.1)
            else:
                break

        proc.poll()
        if proc.returncode is None:
            print('Force kill...')
            try:
                proc.kill()
            except OSError:
                pass

        print('Cleanup done.')

    while True:
        print('Running...')
        start_time = time.time()
        proc = subprocess.Popen(
            [sys.executable, '-m', 'vmchatinput'] + sys.argv[1:]
        )

        proc.communicate()

        if proc.returncode == 0:
            break

        end_time = time.time()

        if end_time - start_time > 60 * 10:
            sleep_time = MIN_SLEEP_TIME

        print('Sleeping...', sleep_time)
        time.sleep(sleep_time)

        sleep_time *= 2
        sleep_time = min(MAX_SLEEP_TIME, sleep_time)
