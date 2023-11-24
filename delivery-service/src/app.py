from flask import Flask, jsonify, request
import os
from flask_cors import CORS
from database import db, Delivery,bcrypt
from redis import Redis
import requests
import json
import threading
import logging

app = Flask(__name__)
    
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] =\
        'sqlite:///' + os.path.join(basedir, 'database.db')
  
db.init_app(app)
bcrypt.init_app(app)

REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
r = Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

@app.route('/deliveries', methods=['POST'])
def create_delivery():
    data = request.json
    new_delivery = Delivery(order_id=data['order_id'], product_id=data['product_id'])
    db.session.add(new_delivery)
    db.session.commit()
    return jsonify(new_delivery.to_dict()), 201

@app.route('/deliveries/<int:delivery_id>', methods=['GET', 'PUT'])
def manage_delivery(delivery_id):
    delivery = Delivery.query.get(delivery_id)

    if request.method == 'GET':
        if delivery:
            return jsonify(delivery.to_dict())
        return jsonify({'error': 'Delivery not found'}), 404

    if request.method == 'PUT':
        data = request.json
        if delivery:
            delivery.status = data.get('status', delivery.status)
            db.session.commit()
            return jsonify(delivery.to_dict())
        return jsonify({'error': 'Delivery not found'}), 404

def handle_inventory_event(message):
    data = json.loads(message['data'])
    order_id = data['order_id']
    product_id = data['product_id']  
    if data['status'] == 'reserved':
        arrange_delivery(order_id, product_id)

def arrange_delivery(order_id, product_id):
    with app.app_context():
        new_delivery = Delivery(order_id=order_id, product_id=product_id, status='arranged')
        db.session.add(new_delivery)
        db.session.commit()
        r.publish('delivery_status', json.dumps({
            'order_id': order_id,
            'product_id': product_id,
            'status': 'SUCCESSFUL' 
        }))

        print(f"Arranged delivery for order {order_id} and product {product_id}")

def start_listeners():
    pubsub = r.pubsub()
    pubsub.subscribe(**{'inventory_update': handle_inventory_event})
    for message in pubsub.listen():
        if message['type'] == 'message':
            handle_inventory_event(message)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()

    listener_thread = threading.Thread(target=start_listeners)
    listener_thread.start()

    app.run(debug=True, port=5003)
