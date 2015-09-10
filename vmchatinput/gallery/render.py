import os

from jinja2 import Environment, FileSystemLoader

from vmchatinput.gallery.catalog import Catalog


class Renderer(object):
    def __init__(self, log_dir, output_dir):
        self._log_dir = log_dir
        self._output_dir = output_dir
        self._environment = Environment(
            autoescape=True,
            loader=FileSystemLoader(
                os.path.join(os.path.dirname(__file__), 'templates'))
        )
        self._catalog = Catalog(log_dir)

    def render(self):
        self._catalog.populate()
        self._render_index()

    def _render_index(self):
        index_template = self._environment.get_template('index.html')
        path = os.path.join(self._output_dir, 'index.html')

        with open(path, 'w') as file:
            file.write(index_template.render(
                index_list_items=self._catalog.get_daily_listing()
            ))
