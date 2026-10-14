from flask import Flask, request, jsonify, url_for
from flask_cors import CORS
from dotenv import load_dotenv
import os
from pymongo import MongoClient

#Carregar as variaveis do .env
load_dotenv()

mongo_uri = os.getenv("MONGO_URI")
client = MongoClient(mongo_uri)
db = client.get_default_database() #Conectar ao banco de dados com uri do .env

app = Flask(__name__)

# Liberar para que o React consuma a nossa API 
CORS(app)