import requests
from app import app
import logging
import time
import functools
from NeedleRef.config import UNSPLASH_KEY

# Cache mechanism for API responses
cache = {}
CACHE_DURATION = 300  # Cache duration in seconds (5 minutes)

def build_request(query, per_page=20, page=1):
    """
    Build URL and headers for Unsplash API request without making the request
    
    Args:
        query (str): The search query
        per_page (int): Number of results to return
        page (int): Page number for pagination
        
    Returns:
        tuple: (url, headers) ready for making a request
    """
    # Try first from .env file via config module
    api_key = UNSPLASH_KEY
    # Fall back to app config if not in .env
    if not api_key:
        api_key = app.config.get('UNSPLASH_API_KEY', '')
    
    if not api_key:
        logging.error("Missing Unsplash API key in environment and configuration")
        return '', {}
        
    base_url = 'https://api.unsplash.com/search/photos'
    
    params = {
        'query': query,
        'per_page': min(per_page, 30),  # Ensure we don't exceed API limits
        'page': max(1, page),  # Ensure page is at least 1
        'content_filter': 'high',  # Filter to avoid explicit content
    }
    
    # Build URL with query parameters
    url = f"{base_url}?{'&'.join([f'{k}={v}' for k, v in params.items()])}"
    
    headers = {
        'Authorization': f'Client-ID {api_key}'
    }
    
    return url, headers

# Tracking for API calls instead of sleeping
def rate_limited(max_per_hour=50):  # Unsplash has a limit of 50 requests per hour
    """
    Decorator to track API calls and add rate limit headers
    Important: This doesn't sleep but tracks the rate and logs warnings
    """
    min_interval = 3600.0 / max_per_hour
    
    def decorator(func):
        last_time_called = [0.0]
        call_count = [0]
        
        @functools.wraps(func)
        def rate_limited_function(*args, **kwargs):
            current_time = time.time()
            elapsed = current_time - last_time_called[0]
            
            # Check if we should be rate limiting
            if elapsed < min_interval:
                call_count[0] += 1
                # Just log a warning instead of sleeping
                logging.warning(f"Rate limit approaching: {call_count[0]} calls in {elapsed:.2f}s")
                if call_count[0] > max_per_hour / 10:  # If making too many calls too quickly
                    logging.warning(f"High API usage detected. Consider adding more caching.")
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

def validate_unsplash_api_key():
    """
    Validate the Unsplash API key by making a test request
    
    Returns:
        bool: True if the API key is valid, False otherwise
    """
    try:
        # Try first from .env file via config module
        api_key = UNSPLASH_KEY
        # Fall back to app config if not in .env
        if not api_key:
            api_key = app.config.get('UNSPLASH_API_KEY')
        
        if not api_key:
            logging.error("❌ Unsplash API key is missing in environment and configuration")
            return False
            
        # Update app config with key from .env if found
        if api_key and UNSPLASH_KEY:
            app.config['UNSPLASH_API_KEY'] = UNSPLASH_KEY
            
        headers = {'Authorization': f'Client-ID {api_key}'}
        test_url = 'https://api.unsplash.com/photos/random?count=1'
        
        # Set a reasonable timeout
        response = requests.get(test_url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            logging.info("✅ Unsplash API key validated successfully")
            return True
        elif response.status_code == 401:
            logging.error(f"❌ Unsplash API key is invalid or unauthorized: {response.status_code}")
            return False
        elif response.status_code == 403:
            logging.warning(f"❌ Unsplash API rate limit exceeded or access forbidden: {response.status_code}")
            return False
        else:
            logging.warning(f"❌ Unsplash API key validation failed: {response.status_code} - {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        logging.error("❌ Timeout when connecting to Unsplash API")
        return False
    except requests.exceptions.ConnectionError:
        logging.error("❌ Connection error when connecting to Unsplash API")
        return False
    except Exception as e:
        logging.error(f"❌ Error validating Unsplash API key: {str(e)}")
        return False

@rate_limited(max_per_hour=30)  # Conservative rate limit to avoid hitting Unsplash's limits
def search_unsplash(query, per_page=20, page=1):
    """
    Search for images on Unsplash using the provided query
    
    Args:
        query (str): The search query
        per_page (int): Number of results to return
        page (int): Page number for pagination
        
    Returns:
        dict: A dictionary with 'results' (list of images) and 'total_pages'
    """
    # Generate cache key
    cache_key = f"unsplash_search_{query}_{per_page}_{page}"
    
    # Check cache first
    current_time = time.time()
    if cache_key in cache and current_time - cache[cache_key]['time'] < CACHE_DURATION:
        logging.debug(f"Using cached results for Unsplash query: '{query}' page {page}")
        return cache[cache_key]['data']
    
    # If not in cache or cache expired, make the API request
    try:
        # Try first from .env file via config module
        api_key = UNSPLASH_KEY
        # Fall back to app config if not in .env
        if not api_key:
            api_key = app.config.get('UNSPLASH_API_KEY', '')
        
        if not api_key:
            logging.error("Missing Unsplash API key in environment and configuration")
            return {'results': [], 'total_pages': 0}
            
        base_url = 'https://api.unsplash.com/search/photos'
        
        params = {
            'query': query,
            'per_page': min(per_page, 30),  # Ensure we don't exceed API limits
            'page': max(1, page),  # Ensure page is at least 1
            'content_filter': 'high',  # Filter to avoid explicit content
        }
        
        headers = {
            'Authorization': f'Client-ID {api_key}'
        }
        
        # Make the request with timeout
        response = requests.get(base_url, params=params, headers=headers, timeout=10)
        
        # Handle rate limiting specifically
        if response.status_code == 429:
            logging.warning("Unsplash API rate limit exceeded. Waiting before retrying.")
            time.sleep(5)  # Wait longer for Unsplash as they have stricter limits
            return search_unsplash(query, per_page, page)  # Retry the request
            
        response.raise_for_status()
        
        # Parse response JSON
        data = response.json()
        results = data.get('results', [])
        total_pages = data.get('total_pages', 1)
        
        # Add source field to each result to indicate this is from Unsplash
        for result in results:
            result['source'] = 'unsplash'
        
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
        
        logging.debug(f"Found {len(results)} images for query '{query}' on page {page} of {total_pages}")
        return result
    
    except requests.exceptions.Timeout:
        logging.error(f"Timeout while connecting to Unsplash API for query '{query}'")
        raise Exception("Unsplash API request timed out")
        
    except requests.exceptions.RequestException as e:
        logging.error(f"Error connecting to Unsplash API: {str(e)}")
        raise Exception(f"Failed to connect to Unsplash: {str(e)}")
    
    except ValueError as e:
        logging.error(f"Error parsing Unsplash API response: {str(e)}")
        raise Exception("Failed to parse Unsplash API response")
        
    except Exception as e:
        logging.error(f"Unexpected error in search_unsplash: {str(e)}")
        raise Exception(f"An unexpected error occurred: {str(e)}")

@rate_limited(max_per_hour=30)
def get_image_details(image_id):
    """
    Get detailed information about a specific Unsplash image
    
    Args:
        image_id (str): The Unsplash image ID
        
    Returns:
        dict: Image details
    """
    # Clean up image_id
    if not image_id:
        logging.error("Missing image_id parameter")
        raise ValueError("Image ID is required")
    
    # Generate cache key and check cache first
    cache_key = f"unsplash_image_{image_id}"
    current_time = time.time()
    
    if cache_key in cache and current_time - cache[cache_key]['time'] < CACHE_DURATION:
        logging.debug(f"Using cached results for Unsplash image ID: {image_id}")
        return cache[cache_key]['data']
    
    # If not in cache or cache expired, make the API request
    try:
        # Try first from .env file via config module
        api_key = UNSPLASH_KEY
        # Fall back to app config if not in .env
        if not api_key:
            api_key = app.config.get('UNSPLASH_API_KEY', '')
            
        if not api_key:
            logging.error("Missing Unsplash API key in environment and configuration")
            raise Exception("Unsplash API key is missing")
            
        base_url = f'https://api.unsplash.com/photos/{image_id}'
        headers = {
            'Authorization': f'Client-ID {api_key}'
        }
        
        # Make the request with timeout
        response = requests.get(base_url, headers=headers, timeout=10)
        
        # Handle rate limiting specifically
        if response.status_code == 429:
            logging.warning("Unsplash API rate limit exceeded. Waiting before retrying.")
            time.sleep(5)  # Wait longer for Unsplash as they have stricter limits
            return get_image_details(image_id)  # Retry the request
            
        response.raise_for_status()
        
        # Parse response JSON
        data = response.json()
        
        # Add source field to indicate this is from Unsplash
        data['source'] = 'unsplash'
        
        # Cache the result
        cache[cache_key] = {
            'time': current_time,
            'data': data
        }
        
        return data
    
    except requests.exceptions.Timeout:
        logging.error(f"Timeout while connecting to Unsplash API for image ID: {image_id}")
        raise Exception("Unsplash API request timed out")
        
    except requests.exceptions.RequestException as e:
        logging.error(f"Error connecting to Unsplash API: {str(e)}")
        raise Exception(f"Failed to connect to Unsplash: {str(e)}")
    
    except ValueError as e:
        logging.error(f"Error parsing Unsplash API response for image ID {image_id}: {str(e)}")
        raise Exception("Failed to parse Unsplash API response")
        
    except KeyError as ke:
        logging.error(f"Missing required field in Unsplash API response: {ke}")
        raise Exception(f"Missing data in Unsplash API response: {ke}")
        
    except Exception as e:
        logging.error(f"Unexpected error getting Unsplash image details: {str(e)}")
        raise Exception(f"An unexpected error occurred: {str(e)}")
