"""
Proxy Server for serving private images publicly
Runs as a separate Flask app on port 5001
"""
from flask import Flask, send_file, abort, jsonify
import requests
import io
from datetime import datetime
import logging
from config import config
from tasks import get_proxy_token_data, get_proxy_stats

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.route('/proxy/image/<token>')
def serve_image(token):
    """Serve image through proxy"""
    # Get token data
    token_data = get_proxy_token_data(token)
    
    if not token_data:
        logger.warning(f"Invalid token requested: {token[:8]}...")
        abort(404, "Invalid token")
    
    # Check expiration
    if datetime.now() > token_data['expires']:
        logger.warning(f"Expired token used: {token[:8]}...")
        abort(404, "Token expired")
    
    try:
        # Fetch from source with auth
        headers = {}
        if 'clickup' in token_data['url'].lower():
            headers = {"Authorization": config.CLICKUP_API_TOKEN}
        
        logger.info(f"Fetching image for token {token[:8]}...")
        response = requests.get(
            token_data['url'], 
            headers=headers, 
            timeout=30
        )
        
        if response.status_code != 200:
            logger.error(f"Source returned {response.status_code}")
            abort(response.status_code)
        
        # Determine content type
        content_type = response.headers.get('content-type', 'image/png')
        
        # Serve the image
        return send_file(
            io.BytesIO(response.content),
            mimetype=content_type,
            as_attachment=False,
            download_name=f"image_{token[:8]}.png"
        )
        
    except requests.exceptions.Timeout:
        logger.error(f"Timeout fetching image for {token[:8]}...")
        abort(504, "Gateway timeout")
    except Exception as e:
        logger.error(f"Error serving image: {e}")
        abort(500, str(e))

@app.route('/health')
def health_check():
    """Health check endpoint"""
    stats = get_proxy_stats()
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        **stats
    })

@app.route('/')
def index():
    """Basic info page"""
    return jsonify({
        "service": "ClickUp Image Proxy",
        "status": "running",
        "endpoints": {
            "/proxy/image/<token>": "Serve proxied image",
            "/health": "Health check and stats",
            "/": "This page"
        }
    })

if __name__ == '__main__':
    port = int(config.PROXY_PORT)
    logger.info(f"🌐 Starting proxy server on port {port}")
    app.run(
        host='0.0.0.0',
        port=port,
        debug=False
    )