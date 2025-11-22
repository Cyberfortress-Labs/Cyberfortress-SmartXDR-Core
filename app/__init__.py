"""
Flask application factory for Cyberfortress SmartXDR Core
"""
from flask import Flask
from flask_cors import CORS
from app.core.database import initialize_database


# Global ChromaDB collection instance
collection = None


def create_app():
    """
    Create and configure Flask application
    
    Returns:
        Flask app instance
    """
    app = Flask(__name__)
    
    # Enable CORS for all routes
    CORS(app)
    
    # Configuration
    app.config['JSON_SORT_KEYS'] = False
    app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
    
    # Initialize ChromaDB
    global collection
    collection = initialize_database()
    
    # Register blueprints
    from app.routes.ai import ai_bp
    app.register_blueprint(ai_bp, url_prefix='/api/ai')
    
    @app.route('/health', methods=['GET'])
    def health():
        """Health check endpoint"""
        return {'status': 'healthy', 'service': 'Cyberfortress SmartXDR Core'}, 200
    
    return app


def get_collection():
    """Get the global ChromaDB collection instance"""
    return collection
