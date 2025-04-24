import json
import os
from flask import Flask, request, jsonify

# Create Flask app for health check endpoint
app = Flask(__name__)

# Health check endpoint
@app.route('/', methods=['GET'])
def index():
    return jsonify({
        'status': 'healthy',
        'service': 'ledger',
        'version': os.environ.get('K_REVISION', 'local')
    }), 200

@app.route('/trigger', methods=['POST'])
def trigger():
    try:
        data = request.json
        action = data.get('action')
        
        if action == 'health_check':
            # Return a simple health check response
            return jsonify({
                'status': 'healthy',
                'service': 'ledger',
                'version': os.environ.get('K_REVISION', 'local')
            }), 200
        else:
            # For other actions, could implement additional functionality
            return jsonify({
                'error': 'Unknown action',
                'action': action
            }), 400
    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500

if __name__ == '__main__':
    # Get the PORT from environment variable (set by Cloud Run)
    port = int(os.environ.get('PORT', 8080))
    
    # Start Flask app
    app.run(host='0.0.0.0', port=port, debug=False) 