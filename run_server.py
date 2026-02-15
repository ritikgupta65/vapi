"""
Simple script to run the Flask server without debug mode restarts
"""
import os
os.environ['FLASK_DEBUG'] = '0'

from app_working import app

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🚀 Starting Speech-to-Speech AI Server")
    print("="*60)
    print("Server running at: http://localhost:5000")
    print("Dashboard:         http://localhost:5000/dashboard")
    print("Test page:         Open test_speech.html in your browser")
    print("="*60 + "\n")
    
    app.run(host="0.0.0.0", port=5000, debug=False)
