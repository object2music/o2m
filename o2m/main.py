from flask import Flask, request, session, redirect
from flask_session import Session
from flask_cors import CORS
from src.dbhandler import DatabaseHandler, Stats, Stats_Raw, Box

api = Flask(__name__)
api.run(host='0.0.0.0', port=6681)
print("test0")
DatabaseHandler.create_box("test", "fdfdf")
print("test1")

@api.route('/test')
def api_box():
    print("test")