from typing import Tuple
from xmlrpc.client import DateTime
import slack
import os
import json
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, g
from slackeventsapi import SlackEventAdapter

# Load Token & Secret Key Env Vars
env_path = Path('.') / '.env'
load_dotenv(dotenv_path=env_path)

# Init Flask App & Slack Client
app = Flask(__name__)
slack_event_adapter = SlackEventAdapter(
    os.environ['SIGNING_SECRET'], '/slack/events', app)
client = slack.WebClient(token=os.environ['SLACK_TOKEN'])
BOT_ID = client.api_call("auth.test")['user_id']

# Commands (Lowercase)
ALPHA_BOT = 'alphabot'
CHECK_OUT = 'checkout'
CHECK_IN = 'checkin'
FORCE = '-force'
HELP = 'help'
STATUS = 'status'

# Help Message
HELP_MSG = """
Supported Commands:
    `status` : Returns the status of the FlatSat remote workstation e.g. `alphabot status`\n
    `checkout` : Attempts to check out the FlatSat remote workstation e.g. `alphabot checkout`\n
        -force: Force check out to the current user e.g. `alphabot checkout -force`\n
    `checkin` : Attempts to check in the FlatSat remote workstation to make it available again e.g. `alphabot checkin`\n
        -force: Force check in the remote workstation e.g. `alphabot checkin -force`\n
    `help` : Displays this help message\n
"""

# Local Data Storage
CHECKOUT_LOG = "checkout.log"  # Store Checkout Status in Local Log File
MESSAGE_LOG = "usage.log"  # Store Messages for Debugging


@slack_event_adapter.on('message')
def message(payload):
    event = payload.get('event', {})
    channel_id = event.get('channel')
    user_id = event.get('user')
    text = event.get('text').lower()

    user_name = get_user_name(user_id)

    if BOT_ID != user_id and ALPHA_BOT in text:
        log_message(user_name, text)
        if CHECK_OUT in text:  # Attempt Checkout of Remote Machine
            execute_checkout(channel_id, text, user_name)
        elif CHECK_IN in text:  # Attempt Check in of Remote Machine
            execute_checkin(channel_id, text, user_name)
        elif HELP in text:  # Display Help
            client.chat_postMessage(channel=channel_id, text=HELP_MSG)
        elif STATUS in text:
            execute_status(channel_id)
        else:
            client.chat_postMessage(
                channel=channel_id, text="Unknown Command - Try `alphabot help` to see supported commands")


def execute_checkin(channel_id, text, user_name):
    rm_checked_out_by, time = get_check_out_status()
    if user_name == rm_checked_out_by:
        rm_checked_out_by = None
        client.chat_postMessage(
            channel=channel_id, text="Check In Successful - FlatSat Workstation is now Available")
    elif FORCE in text:
        rm_checked_out_by = None
        client.chat_postMessage(
            channel=channel_id, text="Force Check In Successful - FlatSat Workstation is now available")
    else:
        client.chat_postMessage(
            channel=channel_id, text="Check In Failed - FlatSat Workstation is use by: "+rm_checked_out_by)
    set_check_out_status(rm_checked_out_by)


def execute_checkout(channel_id, text, user_name):
    rm_checked_out_by, time = get_check_out_status()
    if rm_checked_out_by == None:
        rm_checked_out_by = user_name
        client.chat_postMessage(channel=channel_id, text="Checkout Successful - FlatSat Workstation Checked out by: "
                                + rm_checked_out_by)
    elif FORCE in text:
        rm_checked_out_by = user_name
        client.chat_postMessage(
            channel=channel_id, text="Force Checkout Successful - FlatSat Workstation Checked out by: " + rm_checked_out_by)
    else:
        time_delta = datetime.now() - time
        client.chat_postMessage(
            channel=channel_id, text="Checkout Failed - FlatSat Workstation is use by: " +
            rm_checked_out_by + " ({:.1f} min)".format(time_delta.seconds / 60))
    set_check_out_status(rm_checked_out_by)


def execute_status(channel_id):
    rm_checked_out_by, time = get_check_out_status()
    if rm_checked_out_by is None:
        client.chat_postMessage(
            channel=channel_id, text="FlatSat Workstation is available!")
    else:
        time_delta = datetime.now() - time
        client.chat_postMessage(
            channel=channel_id, text="FlatSat Workstation is use by: " +
            rm_checked_out_by + " ({:.1f} min)".format(time_delta.seconds / 60))


def get_user_name(user_id: str) -> str:
    response = client.api_call("users.info", data={'user': user_id})
    if response['ok']:
        user_data = response['user']
        return user_data['real_name']
    else:
        return "Unknown User ID"  # TODO: Return Request Error


def get_check_out_status() -> Tuple[str, DateTime]:
    with open(CHECKOUT_LOG, 'r') as f:
        last = f.readlines()[-1]
        user = last.split(",")[0]
        timeStr = last.split(",")[1]
        if user == "None":
            return None, None
        else:
            return user, datetime.fromisoformat(timeStr)


def set_check_out_status(user_name: str):
    with open(CHECKOUT_LOG, 'w') as f:
        if user_name is None:
            user_name = "None"
        data = [user_name, datetime.now().isoformat()]
        f.write(",".join(data))


def log_message(user_name, text):
    with open(MESSAGE_LOG, 'a+') as f:
        if user_name is not None:
            data = [user_name, datetime.now().isoformat(), text]
            f.write(",".join(data)+"\n")


if __name__ == "__main__":
    if not Path(CHECKOUT_LOG).is_file():
        set_check_out_status(None)
    app.run(debug=True, port=8000)
