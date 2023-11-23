from flask import Flask, jsonify, request
import os
from flask_cors import CORS
from delivery.delivery_service import delivery_service
from database import db, bcrypt

def create_app() -> Flask:
    """Create flask app."""
    app = Flask(__name__)
    
    CORS(app)
    app.secret_key = os.environ.get("SECRET_KEY", 'your_secret_key')
    app.register_blueprint(delivery_service)
    ORDER_SERVICE_URL = "http://127.0.0.1:8080" 
    PAYMENT_SERVICE_URL = "http://127.0.0.1:8081" 
    INVENTORY_SERVICE_URL = "http://127.0.0.1:8082" 

    basedir = os.path.abspath(os.path.dirname(__file__))
    app.config['SQLALCHEMY_DATABASE_URI'] =\
        'sqlite:///' + os.path.join(basedir, 'database.db')
  
    db.init_app(app)
    bcrypt.init_app(app)


    with app.app_context():
        db.create_all()

    return app

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8083))
    app.run(port=port, debug=True, host='0.0.0.0')
