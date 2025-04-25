import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy.orm import DeclarativeBase

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Create Base class for SQLAlchemy models
class Base(DeclarativeBase):
    pass

# Initialize SQLAlchemy
db = SQLAlchemy(model_class=Base)

# Create Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev_secret_key")

# Configure the database to use PostgreSQL
database_url = os.environ.get("DATABASE_URL")
if not database_url:
    # Fallback to SQLite for development
    logging.warning("DATABASE_URL not found, falling back to SQLite")
    database_url = "sqlite:///tattoo_reference.db"
else:
    logging.info(f"Using PostgreSQL database: {database_url[:20]}...")

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_size": 10,  # Maximum number of connections
    "pool_recycle": 300,  # Recycle connections after 5 minutes
    "pool_pre_ping": True,  # Check connection validity
    "pool_timeout": 30,  # Connection timeout in seconds
    "max_overflow": 20  # Allow up to 20 connections over pool_size
}
app.config["UNSPLASH_API_KEY"] = os.environ.get("UNSPLASH_API_KEY", "your_unsplash_api_key")
app.config["PEXELS_API_KEY"] = os.environ.get("PEXELS_API_KEY", "your_pexels_api_key")

# Initialize the app with the extensions
db.init_app(app)
migrate = Migrate(app, db)

# Import models here to avoid circular imports
from models import Image, Tag, Favorite
