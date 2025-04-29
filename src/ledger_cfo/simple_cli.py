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

# Add a POST handler for root path to prevent 405 errors
@app.route('/', methods=['POST'])
def root_post():
    try:
        data = request.json
        action = data.get('action')
        
        if action == 'run_audit':
            # Placeholder for audit logic
            return jsonify({
                'status': 'ok',
                'message': 'Audit triggered successfully'
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': 'Unknown action. Use "action": "run_audit" to trigger the audit process.'
            }), 400
    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500

@app.route('/trigger', methods=['POST'])
def trigger():
    return root_post()

if __name__ == '__main__':
    # Get the PORT from environment variable
    port = int(os.environ.get('PORT', 8080))
    
    # Start Flask app
    app.run(host='0.0.0.0', port=port, debug=False) 