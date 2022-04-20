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
    # note: you will not be able to see the log with Ctrl-C, you should use docker stop
    log("Received SIGINT: stopping services after completion of pending jobs or timeout")
    adServices.stop()
    log("Goodbye")
    exit(0)


signal.signal(signal.SIGINT, signal_handler)


@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static', 'logo.jpg', mimetype='image/jpg')


@app.route('/api/getStats')
@catch_error
def get_stats():
    teams = adServices.scoreboardCache.getStats()
    msg = {"teams": teams, "roundNum": adServices.checkScheduler.roundNum,
           "flagLifetime": adServices.checkScheduler.flagLifetime}
    return json_response(msg, status_code=200)


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
    log("Starting server")
    app.run(host='0.0.0.0', port=config['flask']['port'])
