import logging
import os

import flask_profiler

logger = logging.getLogger(__name__)


def setup_profiler(app):
    if not app.config['POLYSWARMD'].profiler_enabled:
        return

    db_uri = os.environ.get('PROFILER_DB_URI')
    if db_uri is None:
        logger.error('Profiler enabled but no db configured')
        return

    app.config['flask_profiler'] = {
        'enabled': True,
        'measurement': True,
        'gui': False,
        'storage': {
            'engine': 'sqlalchemy',
            'db_url': db_uri,
        },
    }

    flask_profiler.init_app(app)
