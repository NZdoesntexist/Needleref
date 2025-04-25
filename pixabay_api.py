"""
Pixabay API integration for NeedleRef
"""
import os
import logging
import requests
import time
from collections import OrderedDict
from functools import wraps
from app import app
from NeedleRef.config import PIXABAY_KEY

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# API configuration
PIXABAY_BASE_URL = "https://pixabay.com/api/"

def build_request(query, per_page=20, page=1):
    """
    Build URL and headers for Pixabay API request without making the request
    
    Args:
        query (str): The search query
        per_page (int): Number of results to return (Pixabay max is 200)
        page (int): Page number for pagination
        
    Returns:
        tuple: (url, headers) ready for making a request
    """
    # Try first from .env file via config module
    api_key = PIXABAY_KEY
    # Fall back to app config if not in .env
    if not api_key:
        api_key = app.config.get('PIXABAY_API_KEY')
        
    if not api_key:
        logger.error("Missing Pixabay API key in environment and configuration")
        return '', {}
    
    # Ensure per_page is at least 3 (Pixabay minimum)
    if per_page < 3:
        per_page = 3
        
    params = {
        "key": api_key,
        "q": query,
        "per_page": per_page,
        "page": page,
        "image_type": "photo",  # photo, illustration, vector
        "safesearch": True,     # Filter out adult content
        "order": "popular"      # popular or latest
    }
    
    # Build URL with query parameters
    param_string = "&".join([f"{k}={v}" for k, v in params.items()])
    url = f"{PIXABAY_BASE_URL}?{param_string}"
    
    # Pixabay uses params rather than headers for authentication
    headers = {}
    
    return url, headers

# Cache for API requests (similar to Unsplash/Pexels implementations)
class LRUCache(OrderedDict):
    def __init__(self, capacity):
        super().__init__()
        self.capacity = capacity
        
    def get(self, key):
        if key not in self:
            return None
        self.move_to_end(key)
        return self[key]
        
    def put(self, key, value):
        if key in self:
            self.move_to_end(key)
        self[key] = value
        if len(self) > self.capacity:
            self.popitem(last=False)

# Create a cache with capacity for 100 requests
PIXABAY_CACHE = LRUCache(100)
LAST_REQUEST_TIME = 0
MIN_REQUEST_INTERVAL = 0.1  # 100ms minimum interval between requests

def rate_limited(max_per_minute=30):
    """
    Decorator to track API call rates and log warnings without blocking
    """
    min_interval = 60.0 / max_per_minute
    
    def decorator(func):
        @wraps(func)
        def rate_limited_function(*args, **kwargs):
            global LAST_REQUEST_TIME
            current_time = time.time()
            elapsed = current_time - LAST_REQUEST_TIME
            
            # Enforce minimum interval between requests
            if elapsed < MIN_REQUEST_INTERVAL:
                time.sleep(MIN_REQUEST_INTERVAL - elapsed)
            
            # Log warning if approaching rate limit
            if elapsed < min_interval:
                calls_per_minute = 60.0 / elapsed if elapsed > 0 else float('inf')
                if calls_per_minute > max_per_minute * 0.8:  # 80% of limit
                    logger.warning(f"Rate limit approaching: {int(calls_per_minute)} calls in {elapsed:.2f}s")
                    logger.warning(f"High API usage detected. Consider adding more caching.")
            
            # Update last request time and execute the function
            LAST_REQUEST_TIME = time.time()
            return func(*args, **kwargs)
        
        return rate_limited_function
    
    return decorator

def validate_pixabay_api_key():
    """
    Validate the Pixabay API key by making a test request
    
    Returns:
        bool: True if the API key is valid, False otherwise
    """
    # Try first from .env file via config module
    api_key = PIXABAY_KEY
    # Fall back to app config if not in .env
    if not api_key:
        api_key = app.config.get('PIXABAY_API_KEY')
        
    if not api_key:
        logger.error("❌ Pixabay API key is missing in environment and configuration")
        return False
        
    # Update app config with key from .env if found
    if api_key and PIXABAY_KEY:
        app.config['PIXABAY_API_KEY'] = PIXABAY_KEY
    
    # Log API key status
    if api_key:
        logger.info("PIXABAY_API_KEY loaded from environment variable")
    
    # Fix: Pixabay requires a minimum of 3 per_page
    params = {
        "key": api_key,
        "q": "test",
        "per_page": 3  # Minimum allowed by Pixabay API
    }
    
    try:
        response = requests.get(PIXABAY_BASE_URL, params=params)
        
        if response.status_code == 200:
            logger.info("✅ Pixabay API key validated successfully")
            return True
        else:
            logger.error(f"❌ Pixabay API key validation failed: {response.status_code}")
            logger.error(f"Error details: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Pixabay API key validation error: {str(e)}")
        return False

@rate_limited(max_per_minute=30)  # Pixabay free tier typically allows 200 requests per hour (about 3.3 per minute)
def search_pixabay(query, per_page=20, page=1):
    """
    Search for images on Pixabay using the provided query
    
    Args:
        query (str): The search query
        per_page (int): Number of results to return (Pixabay max is 200)
        page (int): Page number for pagination
        
    Returns:
        dict: A dictionary with 'results' (list of images) and 'total_pages'
    """
    # Check if API key is available
    # Try first from .env file via config module
    api_key = PIXABAY_KEY
    # Fall back to app config if not in .env
    if not api_key:
        api_key = app.config.get('PIXABAY_API_KEY')
        
    if not api_key:
        return {
            "error": True,
            "message": "Pixabay API key is not configured",
            "results": [],
            "total_pages": 0
        }
    
    # Calculate offset for Pixabay pagination (it uses page_number and per_page)
    # page=1 is the first page, page=2 is the second page, etc.
    
    # Check if result is in cache
    cache_key = f"pixabay_{query}_{per_page}_{page}"
    cached_result = PIXABAY_CACHE.get(cache_key)
    if cached_result:
        logger.info(f"Cache hit for Pixabay query: {query}")
        return cached_result
    
    # Pixabay search parameters
    # See documentation: https://pixabay.com/api/docs/
    # Ensure per_page is at least 3 (Pixabay minimum)
    if per_page < 3:
        per_page = 3
        
    params = {
        "key": api_key,
        "q": query,
        "per_page": per_page,
        "page": page,
        "image_type": "photo",  # photo, illustration, vector
        "safesearch": True,     # Filter out adult content
        "order": "popular"      # popular or latest
    }
    
    try:
        response = requests.get(PIXABAY_BASE_URL, params=params)
        
        if response.status_code != 200:
            logger.error(f"Pixabay API error: {response.status_code}")
            logger.error(f"Error details: {response.text}")
            return {
                "error": True,
                "message": f"Pixabay API error: {response.status_code}",
                "results": [],
                "total_pages": 0
            }
        
        data = response.json()
        total_hits = data.get("totalHits", 0)
        total_pages = (total_hits + per_page - 1) // per_page  # Ceiling division
        
        # Process and format the results to match our app's expected structure
        results = []
        
        # Check if we have any results
        if not data.get("hits"):
            logger.info(f"No results found on Pixabay for query: {query}")
            return {
                "results": [],
                "page": page,
                "total_pages": 0,
                "has_more": False,
                "source": "pixabay"
            }
        
        for hit in data["hits"]:
            try:
                # Extract image ID
                image_id = f"pixabay_{hit['id']}"
                
                # Extract image URLs - Pixabay provides multiple sizes
                image_url = hit.get("largeImageURL", "")
                thumbnail_url = hit.get("previewURL", "")
                
                # Extract image dimensions
                width = hit.get("imageWidth", 0)
                height = hit.get("imageHeight", 0)
                
                # Extract description/title - Pixabay uses "tags" as keywords
                tags = hit.get("tags", "").split(", ")
                # Use tags as description if available
                description = ", ".join(tags) if tags else "Pixabay image"
                
                # Extract author info
                author = hit.get("user", "")
                author_username = hit.get("user_id", "")
                
                # Create properly formatted tags for our app
                tag_objects = [{"title": tag.strip()} for tag in tags if tag.strip()]
                
                # Format the result to match our app's expected structure
                result = {
                    "id": image_id,
                    "unsplash_id": image_id,  # For compatibility with existing code
                    "description": description,
                    "url": image_url,
                    "thumbnail_url": thumbnail_url,
                    "width": width,
                    "height": height,
                    "source": "pixabay",
                    "author": author,
                    "author_username": str(author_username),
                    "tags": tag_objects,
                    # Pixabay specific fields
                    "page_url": hit.get("pageURL", ""),
                    "views": hit.get("views", 0),
                    "downloads": hit.get("downloads", 0),
                    "likes": hit.get("likes", 0)
                }
                
                results.append(result)
            except Exception as e:
                logger.error(f"Error processing Pixabay result: {str(e)}")
                continue
        
        # Create response object
        response_data = {
            "results": results,
            "page": page,
            "total_pages": total_pages,
            "has_more": page < total_pages,
            "total_hits": total_hits,
            "source": "pixabay"
        }
        
        # Save to cache
        PIXABAY_CACHE.put(cache_key, response_data)
        
        logger.info(f"Found {len(results)} images from Pixabay for query '{query}'")
        return response_data
        
    except Exception as e:
        logger.error(f"Pixabay API search error: {str(e)}")
        return {
            "error": True,
            "message": f"Pixabay API error: {str(e)}",
            "results": [],
            "total_pages": 0
        }

def get_image_details(image_id):
    """
    Get detailed information about a specific Pixabay image
    
    Args:
        image_id (str): The Pixabay image ID (with or without 'pixabay_' prefix)
        
    Returns:
        dict: Image details
    """
    # Check if API key is available
    # Try first from .env file via config module
    api_key = PIXABAY_KEY
    # Fall back to app config if not in .env
    if not api_key:
        api_key = app.config.get('PIXABAY_API_KEY')
        
    if not api_key:
        return {
            "error": True,
            "message": "Pixabay API key is not configured"
        }
    
    # Remove 'pixabay_' prefix if present
    if image_id.startswith("pixabay_"):
        image_id = image_id[8:]
    
    # Check if result is in cache
    cache_key = f"pixabay_details_{image_id}"
    cached_result = PIXABAY_CACHE.get(cache_key)
    if cached_result:
        logger.info(f"Cache hit for Pixabay image details: {image_id}")
        return cached_result
    
    # Pixabay doesn't have a direct endpoint to fetch a single image by ID
    # We'll use the search endpoint with id parameter
    params = {
        "key": api_key,
        "id": image_id
    }
    
    try:
        response = requests.get(PIXABAY_BASE_URL, params=params)
        
        if response.status_code != 200:
            logger.error(f"Pixabay API error: {response.status_code}")
            logger.error(f"Error details: {response.text}")
            return {
                "error": True,
                "message": f"Pixabay API error: {response.status_code}"
            }
        
        data = response.json()
        
        # Check if we found the image
        if not data.get("hits") or len(data["hits"]) == 0:
            return {
                "error": True,
                "message": f"Image with ID {image_id} not found on Pixabay"
            }
        
        # Get the first hit (should be only one since we searched by ID)
        hit = data["hits"][0]
        
        # Extract image URLs - Pixabay provides multiple sizes
        image_url = hit.get("largeImageURL", "")
        thumbnail_url = hit.get("previewURL", "")
        
        # Extract image dimensions
        width = hit.get("imageWidth", 0)
        height = hit.get("imageHeight", 0)
        
        # Extract description/title - Pixabay uses "tags" as keywords
        tags = hit.get("tags", "").split(", ")
        # Use tags as description if available
        description = ", ".join(tags) if tags else "Pixabay image"
        
        # Extract author info
        author = hit.get("user", "")
        author_username = hit.get("user_id", "")
        
        # Create properly formatted tags for our app
        tag_objects = [{"title": tag.strip()} for tag in tags if tag.strip()]
        
        # Format the result to match our app's expected structure
        result = {
            "id": f"pixabay_{hit['id']}",
            "unsplash_id": f"pixabay_{hit['id']}",  # For compatibility with existing code
            "description": description,
            "url": image_url,
            "thumbnail_url": thumbnail_url,
            "width": width,
            "height": height,
            "source": "pixabay",
            "author": author,
            "author_username": str(author_username),
            "tags": tag_objects,
            # Pixabay specific fields
            "page_url": hit.get("pageURL", ""),
            "views": hit.get("views", 0),
            "downloads": hit.get("downloads", 0),
            "likes": hit.get("likes", 0)
        }
        
        # Save to cache
        PIXABAY_CACHE.put(cache_key, result)
        
        return result
        
    except Exception as e:
        logger.error(f"Pixabay API get image details error: {str(e)}")
        return {
            "error": True,
            "message": f"Pixabay API error: {str(e)}"
        }