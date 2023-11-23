from flask import Flask, request, jsonify, Blueprint
from database import Delivery, db
from redis import Redis
import requests
import json
import os
import logging
from opentelemetry import trace
from opentelemetry import metrics

delivery_service = Blueprint("delivery_service", __name__)

SECRET_KEY = 'your_secret_key'
REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
ORDER_SERVICE_URL = "http://127.0.0.1:8080" 
PAYMENT_SERVICE_URL = "http://127.0.0.1:8081" 
INVENTORY_SERVICE_URL = "http://127.0.0.1:8082" 

r = Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
pubsub = r.pubsub()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

tracer = trace.get_tracer("...tracer")
meter = metrics.get_meter("...meter")

@delivery_service.route('/deliveries', methods=['POST'])
def create_delivery():
    data = request.json
    new_delivery = Delivery(order_id=data['order_id'])
    db.session.add(new_delivery)
    db.session.commit()
    return jsonify(new_delivery.to_dict()), 201

@delivery_service.route('/deliveries/<int:delivery_id>', methods=['PUT'])
def update_delivery(delivery_id):
    delivery = Delivery.query.get(delivery_id)
    if not delivery:
        return jsonify({'error': 'Delivery not found'}), 404

    data = request.json
    delivery.status = data.get('status', delivery.status)
    db.session.commit()
    return jsonify(delivery.to_dict())

