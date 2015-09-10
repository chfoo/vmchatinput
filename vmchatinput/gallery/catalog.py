import csv
import datetime
import glob
import io
import lzma
import logging
import os
import functools
import sqlite3
import collections

from vmchatinput.compress import IMAGES_COMPRESSED_GLOB
import vmchatinput.util

_logger = logging.getLogger(__name__)


IndexListItem = collections.namedtuple(
    '_IndexListItem',
    ['date_obj', 'num_images']
)


class Catalog(object):
    def __init__(self, log_dir):
        self._log_dir = log_dir
        self._conn = None

    def _create_table(self):
        _logger.debug('Creating table.')

        with self._conn:
            self._conn.execute('PRAGMA journal_mode = WAL')
            self._conn.execute('''
                CREATE TABLE IF NOT EXISTS files
                (filename TEXT PRIMARY KEY ASC,
                date TEXT NOT NULL,
                title TEXT
                )
                ''')

    @classmethod
    def _parse_filename_datetime(cls, filename):
        return datetime.datetime.strptime(
            filename.replace('.c.png', ''), '%Y-%m-%dT%H:%M:%S.%f'
        )

    def _populate_images(self):
        pattern = self._log_dir + IMAGES_COMPRESSED_GLOB
        album_names = set()

        for paths in vmchatinput.util.grouper(glob.iglob(pattern), 1000):
            values = []
            for path in paths:
                if not path:
                    continue
                filename = os.path.basename(path)
                date = self._parse_filename_datetime(filename).date().isoformat()
                values.append((filename, date))
                album_names.add(filename[:10])

            with self._conn:
                _logger.debug('Batch populate images.')
                self._conn.executemany(
                    'INSERT OR IGNORE INTO files (filename, date) VALUES (?, ?)',
                    values
                )

    def _populate_image_titles(self):
        query = self._conn.execute(
            '''SELECT filename FROM files
            WHERE title IS NULL ORDER BY filename ASC'''
        )
        prev_filename_datetime = None
        values = []

        def update():
            with self._conn:
                _logger.debug('Batch update images.')
                self._conn.executemany(
                    '''UPDATE files
                    SET title = ?
                    WHERE filename = ?''',
                    values
                )
                values.clear()

        for row in query:
            filename = row[0]

            _logger.debug('Processing title for %s', filename)

            filename_datetime = self._parse_filename_datetime(filename)

            if not prev_filename_datetime:
                prev_filename_datetime = filename_datetime - datetime.timedelta(minutes=5)

            inputs = self._get_inputs_range(prev_filename_datetime, filename_datetime)
            words = []
            word_counter = collections.Counter()

            for input_datetime, nick, input_str in inputs:
                if input_str.startswith('Word:'):
                    word = input_str[5:]
                    word_counter[word] += 1
                    words.append(word)

            # description = ' '.join(words[-100:])
            title = ' '.join(
                word for word, count in word_counter.most_common(3)
                if count > 1
            )
            values.append((title, filename))

            prev_filename_datetime = filename_datetime

            if len(values) > 100:
                update()

        if values:
            update()

    def _get_inputs_range(self, start_datetime, end_datetime):
        assert start_datetime <= end_datetime, (start_datetime, end_datetime)
        assert end_datetime - start_datetime < datetime.timedelta(days=1)

        rows = self._get_inputs_from_log(start_datetime.date())

        if start_datetime.date() != end_datetime.date():
            rows += self._get_inputs_from_log(end_datetime.date())

        for input_datetime, nick, input_str in rows:
            if start_datetime <= input_datetime <= end_datetime:
                yield input_datetime, nick, input_str

    @functools.lru_cache(maxsize=4)
    def _get_inputs_from_log(self, date):
        path = os.path.join(self._log_dir, date.isoformat() + '.csv')

        if not os.path.exists(path):
            path += '.xz'
            csvfile = io.TextIOWrapper(lzma.open(path), newline='')
        else:
            csvfile = open(path, newline='')

        try:
            reader = csv.reader(csvfile)
            rows = []

            for row in reader:
                try:
                    datetime_str, nick, input_str = row
                    input_datetime = datetime.datetime.strptime(
                        datetime_str, '%Y-%m-%dT%H:%M:%S.%f')
                except ValueError:
                    _logger.exception('Row unpack error %s', row)
                    continue

                rows.append((input_datetime, nick, input_str))

            return tuple(rows)
        finally:
            csvfile.close()

    def populate(self):
        if not self._conn:
            db_path = os.path.join(self._log_dir, 'catalog.db')
            self._conn = sqlite3.connect(db_path)

        _logger.info('Populating image catalog database...')
        self._create_table()
        self._populate_images()
        self._populate_image_titles()
        _logger.info('Image catalog database done.')

    def get_daily_listing(self):
        rows = self._conn.execute('''
            SELECT date, count(date) FROM files
            GROUP BY date ORDER BY date DESC
            ''')

        for row in rows:
            date_obj = datetime.datetime.strptime(row[0], '%Y-%m-%d').date()
            yield IndexListItem(date_obj, row[1])
