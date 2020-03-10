from flask import Blueprint, current_app as app

from polyswarmd.utils.response import success

status: Blueprint = Blueprint('status', __name__)


@status.route('')
def status():
    config = app.config['POLYSWARMD']
    return success(config.status.get_status())
