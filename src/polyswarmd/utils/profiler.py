import logging

import flask_profiler

logger = logging.getLogger(__name__)


def setup_profiler(app):
    profiler = app.config['POLYSWARMD'].profiler
    if not profiler.enabled:
        return

    if profiler.db_uri is None:
        logger.error('Profiler enabled but no db configured')
        return

    app.config['flask_profiler'] = {
        'enabled': True,
        'measurement': True,
        'gui': False,
        'storage': {
            'engine': 'sqlalchemy',
            'db_url': profiler.db_uri,
        },
    }

    flask_profiler.init_app(app)
