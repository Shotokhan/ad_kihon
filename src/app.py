from flask import Flask, request, send_from_directory
import signal

from project_utils import read_config, catch_error, init_or_resume_mongo, json_response, log
from services import Services
from submission_service import RateLimitExceeded, InvalidToken, OutOfTimeWindow


app = Flask(__name__)
config = read_config()
app.config.update(config['flask'])
init_or_resume_mongo(config)
adServices = Services(config)


def signal_handler(sig, frame):
    log("Received SIGINT: stopping services after completion of pending jobs or timeout")
    adServices.stop()
    log("Goodbye")
    exit(0)


signal.signal(signal.SIGINT, signal_handler)

# TODO: integration test of Services, separated from app.py


@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/api/getStats')
@catch_error
def get_stats():
    teams = adServices.scoreboardCache.getStats()
    return json_response(teams, 200)


@app.route('/api/flagSubmit', methods=['POST'])
@catch_error
def flag_submit():
    data = request.get_json(force=True, silent=True)
    if data is None:
        return json_response({"error": "Input data is not json"}, status_code=400)
    else:
        try:
            token, flags = data['token'], data['flags']
        except KeyError:
            return json_response({"error": "token or flags fields missing"}, status_code=400)
        if not isinstance(token, str):
            return json_response({"error": "token must be a string"}, status_code=400)
        if not isinstance(flags, list):
            return json_response({"error": "flags must be a list"}, status_code=400)
        try:
            msg = adServices.submissionService.submitFlags(token, flags)
        except RateLimitExceeded:
            return json_response({"error": "Rate limit exceeded"}, status_code=400)
        except InvalidToken:
            return json_response({"error": "Invalid token"}, status_code=400)
        except OutOfTimeWindow:
            return json_response({"error": "Too early or too late to submit a flag"}, status_code=400)
        return json_response(msg, status_code=200)


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)
