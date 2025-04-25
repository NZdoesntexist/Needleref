import requests
import logging
import re
import time
import functools
from app import app
from NeedleRef.config import PEXELS_KEY

from collections import OrderedDict

def build_request(query, per_page=20, page=1):
    """
    Build URL and headers for Pexels API request without making the request
    
    Args:
        query (str): The search query
        per_page (int): Number of results to return
        page (int): Page number for pagination
        
    Returns:
        tuple: (url, headers) ready for making a request
    """
    # Try first from .env file via config module
    api_key = PEXELS_KEY
    # Fall back to app config if not in .env
    if not api_key:
        api_key = app.config.get('PEXELS_API_KEY', '')
        
    if not api_key:
        logging.error("Missing Pexels API key in environment and configuration")
        return '', {}
        
    base_url = 'https://api.pexels.com/v1/search'
    
    params = {
        'query': query,
        'per_page': min(per_page, 80),  # Ensure we don't exceed API limits
        'page': max(1, page)  # Ensure page is at least 1
    }
    
    # Build URL with query parameters
    url = f"{base_url}?{'&'.join([f'{k}={v}' for k, v in params.items()])}"
    
    headers = {'Authorization': api_key}
    
    return url, headers

# LRU Cache implementation
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

# Initialize cache with size limit
cache = LRUCache(1000)  # Store up to 1000 items

# Add a simple cache mechanism for API responses
CACHE_DURATION = 300  # Cache duration in seconds (5 minutes)

# Add a tracking mechanism for API calls that doesn't block requests
def rate_limited(max_per_minute=30):
    """
    Decorator to track API call rates and log warnings without blocking
    """
    min_interval = 60.0 / max_per_minute
    
    def decorator(func):
        last_time_called = [0.0]
        call_count = [0]
        
        @functools.wraps(func)
        def rate_limited_function(*args, **kwargs):
            current_time = time.time()
            elapsed = current_time - last_time_called[0]
            
            # Check if we're making calls too quickly
            if elapsed < min_interval:
                call_count[0] += 1
                # Just log warnings instead of sleeping
                if call_count[0] > 5:  # If making too many calls
                    logging.warning(f"High Pexels API usage: {call_count[0]} calls in {elapsed:.2f}s")
            else:
                # Reset counter if enough time has passed
                call_count[0] = 1
            
            # reset counter hourly
            if elapsed > 3600:
                last_time_called[0] = current_time
                call_count[0] = 0
                
            # Call the function without waiting
            ret = func(*args, **kwargs)
            last_time_called[0] = current_time
            return ret
        
        return rate_limited_function
    
    return decorator

def validate_pexels_api_key():
    """
    Validate the Pexels API key by making a test request
    
    Returns:
        bool: True if the API key is valid, False otherwise
    """
    try:
        # Try first from .env file via config module
        api_key = PEXELS_KEY
        # Fall back to app config if not in .env
        if not api_key:
            api_key = app.config.get('PEXELS_API_KEY')
        
        if not api_key:
            logging.error("❌ Pexels API key is missing in environment and configuration")
            return False
            
        # Update app config with key from .env if found
        if api_key and PEXELS_KEY:
            app.config['PEXELS_API_KEY'] = PEXELS_KEY
        
        # Clean the API key if it contains non-alphanumeric characters (like quotes)
        original_length = len(api_key)
        cleaned_key = re.sub(r'[^a-zA-Z0-9]', '', api_key)
        if original_length != len(cleaned_key):
            logging.warning("Pexels API key contains non-alphanumeric characters, attempting to clean")
            logging.info(f"Cleaned Pexels API key from length {original_length} to {len(cleaned_key)}")
            api_key = cleaned_key
        
        headers = {'Authorization': api_key}
        test_url = 'https://api.pexels.com/v1/search?query=test&per_page=1'
        
        # Set a reasonable timeout
        response = requests.get(test_url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            logging.info("✅ Pexels API key validated successfully")
            return True
        elif response.status_code == 401:
            logging.error(f"❌ Pexels API key is invalid or unauthorized: {response.status_code}")
            return False
        elif response.status_code == 429:
            logging.warning(f"❌ Pexels API rate limit exceeded: {response.status_code}")
            return False
        else:
            logging.warning(f"❌ Pexels API key validation failed: {response.status_code} - {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        logging.error("❌ Timeout when connecting to Pexels API")
        return False
    except requests.exceptions.ConnectionError:
        logging.error("❌ Connection error when connecting to Pexels API")
        return False
    except Exception as e:
        logging.error(f"❌ Error validating Pexels API key: {str(e)}")
        return False

@rate_limited(max_per_minute=20)  # Rate limit Pexels API calls
def search_pexels(query, per_page=20, page=1):
    """
    Search for images on Pexels using the provided query
    
    Args:
        query (str): The search query
        per_page (int): Number of results to return
        page (int): Page number for pagination
        
    Returns:
        dict: A dictionary with 'results' (list of images) and 'total_pages'
    """
    # Generate cache key
    cache_key = f"pexels_search_{query}_{per_page}_{page}"
    
    # Check cache first
    current_time = time.time()
    if cache_key in cache and current_time - cache[cache_key]['time'] < CACHE_DURATION:
        logging.debug(f"Using cached results for Pexels query: '{query}' page {page}")
        return cache[cache_key]['data']
    
    # If not in cache or cache expired, make the API request
    try:
        # Try first from .env file via config module
        api_key = PEXELS_KEY
        # Fall back to app config if not in .env
        if not api_key:
            api_key = app.config.get('PEXELS_API_KEY', '')
            
        if not api_key:
            logging.error("Missing Pexels API key in environment and configuration")
            return {'results': [], 'total_pages': 0}
            
        base_url = 'https://api.pexels.com/v1/search'
        
        params = {
            'query': query,
            'per_page': min(per_page, 80),  # Ensure we don't exceed API limits
            'page': max(1, page)  # Ensure page is at least 1
        }
        
        headers = {'Authorization': api_key}
        
        # Make the request with timeout
        response = requests.get(base_url, params=params, headers=headers, timeout=10)
        
        # Handle different error codes specifically
        if response.status_code == 429:
            logging.warning("Pexels API rate limit exceeded. Waiting before retrying.")
            time.sleep(2)  # Wait briefly before retry
            return search_pexels(query, per_page, page)  # Retry the request
            
        response.raise_for_status()
        
        # Parse response JSON
        data = response.json()
        photos = data.get('photos', [])
        total_results = data.get('total_results', 0)
        
        # Calculate total pages
        total_pages = (total_results + per_page - 1) // per_page
        
        # Transform Pexels format to match our application's format
        results = []
        for photo in photos:
            try:
                # Map Pexels API response to our app's format with defensive coding
                image = {
                    'id': f"pexels_{photo['id']}",  # Prefix with 'pexels_' to differentiate from Unsplash
                    'description': photo.get('alt', '') or query,
                    'width': photo.get('width', 0),
                    'height': photo.get('height', 0),
                    'urls': {
                        'raw': photo.get('src', {}).get('original', ''),
                        'full': photo.get('src', {}).get('original', ''),
                        'regular': photo.get('src', {}).get('large', ''),
                        'small': photo.get('src', {}).get('medium', ''),
                        'thumb': photo.get('src', {}).get('small', '')
                    },
                    'user': {
                        'name': photo.get('photographer', ''),
                        'username': str(photo.get('photographer_id', ''))
                    },
                    'links': {
                        'self': photo.get('url', ''),
                        'download': photo.get('src', {}).get('original', '')
                    },
                    # Add a source field to indicate this is from Pexels
                    'source': 'pexels',
                    # Add tags from query terms
                    'tags': [
                        {'title': tag.strip()} for tag in query.split(' ') if tag.strip()
                    ]
                }
                results.append(image)
            except KeyError as ke:
                logging.warning(f"Skipping Pexels photo due to missing key: {ke}")
                continue
        
        # Create result object
        result = {
            'results': results,
            'total_pages': total_pages
        }
        
        # Cache the result
        cache[cache_key] = {
            'time': current_time,
            'data': result
        }
        
        logging.debug(f"Found {len(results)} Pexels images for query '{query}' on page {page} of {total_pages}")
        return result
    
    except requests.exceptions.Timeout:
        logging.error(f"Timeout while connecting to Pexels API for query '{query}'")
        raise Exception("Pexels API request timed out")
        
    except requests.exceptions.RequestException as e:
        logging.error(f"Error connecting to Pexels API: {str(e)}")
        raise Exception(f"Failed to connect to Pexels: {str(e)}")
    
    except ValueError as e:
        logging.error(f"Error parsing Pexels API response: {str(e)}")
        raise Exception("Failed to parse Pexels API response")
        
    except Exception as e:
        logging.error(f"Unexpected error in search_pexels: {str(e)}")
        raise Exception(f"An unexpected error occurred: {str(e)}")

@rate_limited(max_per_minute=30)
def get_image_details(image_id):
    """
    Get detailed information about a specific Pexels image
    
    Args:
        image_id (str): The Pexels image ID (without 'pexels_' prefix)
        
    Returns:
        dict: Image details
    """
    # Clean up the image_id if needed
    if isinstance(image_id, str) and image_id.startswith('pexels_'):
        image_id = image_id[7:]  # Remove 'pexels_' prefix
    
    # Generate cache key and check cache first
    cache_key = f"pexels_image_{image_id}"
    current_time = time.time()
    
    if cache_key in cache and current_time - cache[cache_key]['time'] < CACHE_DURATION:
        logging.debug(f"Using cached results for Pexels image ID: {image_id}")
        return cache[cache_key]['data']
    
    # If not in cache or cache expired, make the API request
    try:
        # Try first from .env file via config module
        api_key = PEXELS_KEY
        # Fall back to app config if not in .env
        if not api_key:
            api_key = app.config.get('PEXELS_API_KEY', '')
            
        if not api_key:
            logging.error("Missing Pexels API key in environment and configuration")
            raise Exception("Pexels API key is missing")
            
        base_url = f'https://api.pexels.com/v1/photos/{image_id}'
        headers = {'Authorization': api_key}
        
        # Make the request with timeout
        response = requests.get(base_url, headers=headers, timeout=10)
        
        # Handle rate limiting specifically
        if response.status_code == 429:
            logging.warning("Pexels API rate limit exceeded. Waiting before retrying.")
            time.sleep(2)  # Wait briefly
            return get_image_details(image_id)  # Retry the request
            
        response.raise_for_status()
        
        # Parse response JSON and transform to match our app's format
        photo = response.json()
        
        # Use defensive coding with get() and default values
        image = {
            'id': f"pexels_{photo.get('id', image_id)}",
            'description': photo.get('alt', ''),
            'width': photo.get('width', 0),
            'height': photo.get('height', 0),
            'urls': {
                'raw': photo.get('src', {}).get('original', ''),
                'full': photo.get('src', {}).get('original', ''),
                'regular': photo.get('src', {}).get('large', ''),
                'small': photo.get('src', {}).get('medium', ''),
                'thumb': photo.get('src', {}).get('small', '')
            },
            'user': {
                'name': photo.get('photographer', ''),
                'username': str(photo.get('photographer_id', ''))
            },
            'links': {
                'self': photo.get('url', ''),
                'download': photo.get('src', {}).get('original', '')
            },
            'source': 'pexels',
            'tags': []  # Initialize empty tags array
        }
        
        # Cache the result
        cache[cache_key] = {
            'time': current_time,
            'data': image
        }
        
        return image
    
    except requests.exceptions.Timeout:
        logging.error(f"Timeout while connecting to Pexels API for image ID: {image_id}")
        raise Exception("Pexels API request timed out")
        
    except requests.exceptions.RequestException as e:
        logging.error(f"Error connecting to Pexels API: {str(e)}")
        raise Exception(f"Failed to connect to Pexels: {str(e)}")
    
    except ValueError as e:
        logging.error(f"Error parsing Pexels API response for image ID {image_id}: {str(e)}")
        raise Exception("Failed to parse Pexels API response")
        
    except KeyError as ke:
        logging.error(f"Missing required field in Pexels API response: {ke}")
        raise Exception(f"Missing data in Pexels API response: {ke}")
        
    except Exception as e:
        logging.error(f"Unexpected error getting Pexels image details: {str(e)}")
        raise Exception(f"An unexpected error occurred: {str(e)}")