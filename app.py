import json
import os
from flask import Flask, request, jsonify
import subprocess
import threading
import time

# Create Flask app for health check endpoint
app = Flask(__name__)

# Health check endpoint
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

# Start Streamlit in a separate thread
def run_streamlit():
    port = int(os.environ.get('PORT', 8501))
    subprocess.run(["streamlit", "run", "main.py", "--server.port", str(port), "--server.address", "0.0.0.0"])

if __name__ == '__main__':
    # Start Streamlit in a background thread
    streamlit_thread = threading.Thread(target=run_streamlit)
    streamlit_thread.daemon = True
    streamlit_thread.start()
    
    # Give Streamlit time to start
    time.sleep(5)
    
    # Start Flask app on a different port
    port = int(os.environ.get('FLASK_PORT', 8080))
    app.run(host='0.0.0.0', port=port) 