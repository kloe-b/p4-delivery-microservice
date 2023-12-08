from flask import Flask, jsonify, request
import os
from flask_cors import CORS
from database import db, Del,bcrypt
from redis import Redis
import requests
import json
import threading
import logging
from prometheus_client import Counter, generate_latest
from flask import Response
from opentelemetry import trace
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes


service_name = "my-delivery-service" 
resource = Resource(attributes={
    ResourceAttributes.SERVICE_NAME: service_name
})
app = Flask(__name__)

trace.set_tracer_provider(TracerProvider(resource=resource))

otlp_exporter = OTLPSpanExporter(
    endpoint="http://localhost:4317",  
    insecure=True
)

trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(otlp_exporter))

FlaskInstrumentor().instrument_app(app)

tracer = trace.get_tracer(__name__)

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] =\
        'sqlite:///' + os.path.join(basedir, 'database.db')
  
db.init_app(app)
bcrypt.init_app(app)

REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
r = Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger(__name__) 

delivery_creation_counter = Counter('delivery_creation_total', 'Total number of created deliveries')
delivery_arranged_counter = Counter('delivery_arranged_total', 'Total number of arranged deliveries')
delivery_failed_counter = Counter('delivery_failed_total', 'Total number of failed deliveries')

@app.route('/metrics')
def serve_metrics():
    return Response(generate_latest(), mimetype="text/plain")

@app.route('/deliveries', methods=['POST'])
def create_delivery():
    with tracer.start_as_current_span("create_delivery"):
        try:
            data = request.json
            logger.info(f"Received request to create delivery for order_id: {data['order_id']}")
            new_delivery = Del(order_id=data['order_id'], product_id=data['product_id'])
            with tracer.start_as_current_span("db_add_delivery"):
                db.session.add(new_delivery)
                db.session.commit()
            logger.info(f"Delivery for order_id {data['order_id']} created successfully")
            delivery_creation_counter.inc()
            return jsonify(new_delivery.to_dict()), 201
        except Exception as e:
            logger.error(f"Error creating delivery for order_id {data['order_id']}: {e}", exc_info=True)
            delivery_failed_counter.inc()
            span.record_exception(e)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
            return jsonify({'error': 'Failed to create delivery'}), 500

@app.route('/deliveries/<int:delivery_id>', methods=['GET', 'PUT'])
def manage_delivery(delivery_id):
    delivery = Del.query.get(delivery_id)

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
    logger.info(f"Received inventory update message: {message['data']}")
    data = json.loads(message['data'])
    order_id = data['order_id']
    product_id = data['product_id'] 
    quantity=data['quantity'] 
    if data['status'] == 'reserved':
        arrange_delivery(order_id, product_id,quantity)

def arrange_delivery(order_id, product_id,quantity):
    with app.app_context():
        with tracer.start_as_current_span("arrange_delivery") as span:
            span.set_attribute("order_id", order_id)
            span.set_attribute("product_id", product_id)
            span.set_attribute("quantity", quantity)
            
            logger.info(f"Arranging delivery for order_id {order_id}, product_id {product_id}")
            new_delivery = Del(order_id=order_id, product_id=product_id, status='arranged')
            db.session.add(new_delivery)
            db.session.commit()
            r.publish('delivery_status', json.dumps({
                'order_id': order_id,
                'product_id': product_id,
                'status': 'SUCCESSFUL',
                'quantity':quantity 
            }))
            delivery_arranged_counter.inc()
            print(f"Arranged delivery for order {order_id} and product {product_id}")

def start_listeners():
    pubsub = r.pubsub()
    pubsub.subscribe(**{'inventory_update': handle_inventory_event})
    logger.info("Started listeners")
  
    for message in pubsub.listen():
        if message['type'] == 'message':
            handle_inventory_event(message)

if __name__ == '__main__':
    logger.info("Starting Flask application and initializing database")
    with app.app_context():
        db.create_all()
    logger.info("Database initialized")
    thread = threading.Thread(target=start_listeners)
    thread.start()
    logger.info("Background thread for payment status listener started")

    app.run(debug=True, port=5003)
