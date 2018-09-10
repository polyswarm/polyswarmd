from flask import jsonify
from werkzeug.exceptions import default_exceptions, HTTPException


def install_error_handlers(app):
    def make_json_error(e):
        response = jsonify(message=str(e))
        response.status_code = e.code if isinstance(e, HTTPException) else 500
        return response

    for code in default_exceptions:
        app.register_error_handler(code, make_json_error)


def success(result=None):
    if result is not None:
        return jsonify({'status': 'OK', 'result': result}), 200

    return jsonify({'status': 'OK'}), 200


def failure(message, code=500):
    return jsonify({'status': 'FAIL', 'errors': message}), code
