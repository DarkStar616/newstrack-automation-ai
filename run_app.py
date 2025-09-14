import os
import sys
# DON'T CHANGE THIS !!!
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Override environment to enforce live mode defaults (test mode is opt-in only)
# Only override if not explicitly set to true
if os.environ.get('LLM_TEST_MODE', '').lower() != 'true':
    os.environ['LLM_TEST_MODE'] = 'false'
if os.environ.get('SEARCH_TEST_MODE', '').lower() != 'true':
    os.environ['SEARCH_TEST_MODE'] = 'false'

# Set other defaults
os.environ.setdefault('SEARCH_MODE', 'shallow')
os.environ.setdefault('RECENCY_WINDOW_MONTHS', '3')
os.environ.setdefault('SEARCH_PROVIDER', 'google')
os.environ.setdefault('SEARCH_CACHE_TTL_DAYS', '14')
os.environ.setdefault('SEARCH_BYPASS_CACHE', 'false')

from flask import Flask, send_from_directory
from flask_cors import CORS
from src.models.user import db
from src.routes.user import user_bp
from src.routes.newstrack import newstrack_bp
from src.services.batch_service import init_batch_service

# Create Flask app with proper static folder configuration
app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), 'src', 'static'))

# Enable CORS for all routes
CORS(app)

# Configuration from environment variables
app.config['SECRET_KEY'] = os.getenv('APP_SECRET', 'dev-secret-key-change-in-production')
app.config['MODEL_NAME'] = os.getenv('MODEL_NAME', 'gemini-1.5-flash')
app.config['LLM_PROVIDER'] = os.getenv('LLM_PROVIDER', 'google')
app.config['SEARCH_MODE'] = os.getenv('SEARCH_MODE', 'off')

# Register blueprints
app.register_blueprint(user_bp, url_prefix='/api')
app.register_blueprint(newstrack_bp, url_prefix='/api')

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(os.path.dirname(__file__), 'src', 'database', 'app.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)
with app.app_context():
    db.create_all()
    # Initialize batch service with Flask app context
    init_batch_service(app)

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

if __name__ == '__main__':
    # Configure logging to stdout for debugging
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        stream=sys.stdout
    )
    app.logger.setLevel(logging.INFO)
    app.logger.propagate = True
    
    # Log search configuration at startup
    from src.utils.config import log_search_config
    log_search_config()
    
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

