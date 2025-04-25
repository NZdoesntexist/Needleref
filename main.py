import logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

import os
import sys
from app import app  # noqa: F401
import routes  # noqa: F401
from NeedleRef.routes import api_bp
from models import update_sqlite_db
from NeedleRef.apis.pexels_api import validate_pexels_api_key
from NeedleRef.apis.unsplash_api import validate_unsplash_api_key
from NeedleRef.apis.pixabay_api import validate_pixabay_api_key

# Note: Root route is handled in routes.py

# Register API Blueprint
app.register_blueprint(api_bp)

# Configure Flask app logging
app.logger.setLevel(logging.DEBUG)

# Ensure necessary environment variables are set
if 'PEXELS_API_KEY' not in app.config or not app.config.get('PEXELS_API_KEY'):
    pexels_key = os.environ.get('PEXELS_API_KEY')
    if pexels_key:
        app.config['PEXELS_API_KEY'] = pexels_key
        logging.info("PEXELS_API_KEY loaded from environment variable")
    else:
        logging.warning("⚠️ PEXELS_API_KEY not found in environment or configuration")
        app.config['PEXELS_API_KEY'] = ''  # Set empty default to avoid errors

if 'UNSPLASH_API_KEY' not in app.config or not app.config.get('UNSPLASH_API_KEY'):
    unsplash_key = os.environ.get('UNSPLASH_API_KEY')
    if unsplash_key:
        app.config['UNSPLASH_API_KEY'] = unsplash_key
        logging.info("UNSPLASH_API_KEY loaded from environment variable")
    else:
        logging.warning("⚠️ UNSPLASH_API_KEY not found in environment or configuration")
        app.config['UNSPLASH_API_KEY'] = ''  # Set empty default to avoid errors

if 'PIXABAY_API_KEY' not in app.config or not app.config.get('PIXABAY_API_KEY'):
    pixabay_key = os.environ.get('PIXABAY_API_KEY')
    if pixabay_key:
        app.config['PIXABAY_API_KEY'] = pixabay_key
        logging.info("PIXABAY_API_KEY loaded from environment variable")
    else:
        logging.warning("⚠️ PIXABAY_API_KEY not found in environment or configuration")
        app.config['PIXABAY_API_KEY'] = ''  # Set empty default to avoid errors

# Set default database configuration if not already set
if 'SQLALCHEMY_TRACK_MODIFICATIONS' not in app.config:
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Log database path for debugging
logging.info(f"SQLite DB Path: {os.path.abspath('instance/tattoo_reference.db')}")
logging.info(f"Using PostgreSQL database: {app.config['SQLALCHEMY_DATABASE_URI'].split('@')[0]}...")

# Initialize/update SQLite database schema
try:
    update_sqlite_db()
except Exception as e:
    logging.error(f"❌ Error initializing SQLite database: {str(e)}")
    logging.error("Application may not function correctly without proper database setup")

# Validate API keys
pexels_valid = validate_pexels_api_key()
unsplash_valid = validate_unsplash_api_key()
pixabay_valid = validate_pixabay_api_key()

# Check if at least one API is valid
if not any([pexels_valid, unsplash_valid, pixabay_valid]):
    logging.warning("❌ No API keys are valid (Pexels, Unsplash, Pixabay).")
    logging.warning("The application will have limited functionality without valid API keys.")
    logging.warning("Please check your environment variables or configuration.")
else:
    # Log individual API statuses
    if not pexels_valid:
        logging.warning("❌ Pexels API key is invalid or missing. Some features will be limited.")
    if not unsplash_valid:
        logging.warning("❌ Unsplash API key is invalid or missing. Some features will be limited.")
    if not pixabay_valid:
        logging.warning("❌ Pixabay API key is invalid or missing. Some features will be limited.")
    
    # Log success message if at least one API is valid
    logging.info(f"✅ API key status: Pexels: {'✓' if pexels_valid else '✗'}, Unsplash: {'✓' if unsplash_valid else '✗'}, Pixabay: {'✓' if pixabay_valid else '✗'}")
    logging.info("✅ Application is functional with available APIs.")

if __name__ == "__main__":
    try:
        # Ensure we're binding to all interfaces
        app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=True)
    except Exception as e:
        logging.error(f"Failed to start server: {e}")
        logging.error("Check if port 5000 is already in use")
        sys.exit(1)
