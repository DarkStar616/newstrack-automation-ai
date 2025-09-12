import os
import sys
import uuid
import time
# DON'T CHANGE THIS !!!
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, send_from_directory, request, g
from flask_cors import CORS
from src.models.user import db
from src.routes.user import user_bp
from src.routes.newstrack import newstrack_bp
from src.utils.error_handler import register_error_handlers

# Create Flask app with proper static folder configuration
app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), 'static'))

# Enable CORS for all routes
CORS(app)

# Configuration from environment variables
app.config['SECRET_KEY'] = os.getenv('APP_SECRET', 'dev-secret-key-change-in-production')
app.config['MODEL_NAME'] = os.getenv('MODEL_NAME', 'gpt-4.1-mini')
app.config['LLM_PROVIDER'] = os.getenv('LLM_PROVIDER', 'openai')
app.config['SEARCH_MODE'] = os.getenv('SEARCH_MODE', 'off')

# Register error handlers
register_error_handlers(app)

# Add request ID and timestamp middleware
@app.before_request
def before_request():
    g.request_id = str(uuid.uuid4())
    g.request_timestamp = time.time()
    app.config['REQUEST_ID'] = g.request_id
    app.config['REQUEST_TIMESTAMP'] = g.request_timestamp
    # Store request_id in config instead of direct assignment
    app.config['CURRENT_REQUEST_ID'] = g.request_id
    
    # Log request
    app.logger.info(f"Request {g.request_id}: {request.method} {request.path}")

@app.after_request
def after_request(response):
    # Log response
    duration = time.time() - g.request_timestamp
    app.logger.info(f"Response {g.request_id}: {response.status_code} ({duration:.3f}s)")
    
    # Add request ID to response headers
    response.headers['X-Request-ID'] = g.request_id
    return response

# Register blueprints
app.register_blueprint(user_bp, url_prefix='/api')
app.register_blueprint(newstrack_bp, url_prefix='/api')

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(os.path.dirname(__file__), 'database', 'app.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)
with app.app_context():
    db.create_all()

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    static_folder_path = app.static_folder
    if static_folder_path is None:
        return "Static folder not configured", 404

    if path != "" and os.path.exists(os.path.join(static_folder_path, path)):
        return send_from_directory(static_folder_path, path)
    else:
        index_path = os.path.join(static_folder_path, 'index.html')
        if os.path.exists(index_path):
            return send_from_directory(static_folder_path, 'index.html')
        else:
            return "index.html not found", 404

# Note: This file now only creates the app but doesn't run it
# Use run_app.py to actually start the server
