from flask import jsonify, request
from werkzeug.exceptions import HTTPException


class ApiError(Exception):
    """Error with a message safe to show the user."""

    def __init__(self, status, message, fields=None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.fields = fields


class ValidationError(Exception):
    def __init__(self, fields):
        super().__init__("Some fields need attention.")
        self.fields = fields


def _is_api():
    return request.path.startswith("/api/")


def register_errors(app):
    @app.errorhandler(ApiError)
    def api_error(err):
        body = {"error": err.message}
        if err.fields:
            body["fields"] = err.fields
        return jsonify(body), err.status

    @app.errorhandler(ValidationError)
    def validation_error(err):
        return jsonify({"error": "Some fields need attention.", "fields": err.fields}), 422

    @app.errorhandler(HTTPException)
    def http_error(err):
        if not _is_api():
            return err
        messages = {
            404: "That doesn’t exist.",
            405: "That method isn’t allowed here.",
            413: "That upload is too large.",
        }
        return jsonify({"error": messages.get(err.code, err.description)}), err.code

    @app.errorhandler(Exception)
    def unexpected(err):
        if app.debug or not _is_api():
            raise err
        app.logger.exception("Unhandled error on %s %s", request.method, request.path)
        return jsonify({"error": "Something went wrong on the server. Try again."}), 500
