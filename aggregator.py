import asyncio
import httpx
import logging
import traceback
from .unsplash_api import build_request as u_req
from .pexels_api import build_request as p_req
from .pixabay_api import build_request as x_req

# Dictionary mapping source names to their respective build_request functions
REQ = {"unsplash": u_req, "pexels": p_req, "pixabay": x_req}

async def _fetch(c, url, headers, source, query):
    """
    Helper function to make an HTTP request and return JSON response
    
    Args:
        c (httpx.AsyncClient): Async HTTP client
        url (str): Request URL
        headers (dict): Request headers
        source (str): Name of the source API
        query (str): The query being searched
        
    Returns:
        tuple: (source, query, response_data or None)
    """
    try:
        logging.info(f"Fetching from {source} API with query '{query}' - URL: {url}")
        r = await c.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        logging.info(f"Successfully retrieved data from {source} for query '{query}'")
        return source, query, data
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code
        logging.error(f"HTTP error {status_code} from {source} API for query '{query}': {str(e)}")
        return source, query, None
    except httpx.RequestError as e:
        logging.error(f"Request error from {source} API for query '{query}': {str(e)}")
        return source, query, None
    except Exception as e:
        error_details = traceback.format_exc()
        logging.error(f"Unexpected error from {source} API for query '{query}': {str(e)}\n{error_details}")
        return source, query, None

async def multi_source(queries, sources=("unsplash", "pexels", "pixabay")):
    """
    Fetch images from multiple sources concurrently
    
    Args:
        queries (list): List of search queries
        sources (tuple): Tuple of source names to use (default: all three APIs)
        
    Returns:
        list: Combined results from all sources
    """
    results = []
    errors = []
    
    logging.info(f"Starting concurrent search with {len(queries)} queries across sources: {', '.join(sources)}")
    
    # Make sure we have at least one valid source
    valid_sources = [s for s in sources if s in REQ]
    if not valid_sources:
        logging.error(f"No valid sources found. Requested: {sources}, Available: {list(REQ.keys())}")
        return []
    
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            # Create a task for each query-source combination
            tasks = []
            for q in queries:
                for s in valid_sources:
                    try:
                        url, headers = REQ[s](q)
                        if url and headers is not None:  # Check if request build was successful
                            tasks.append(_fetch(c, url, headers, s, q))
                        else:
                            logging.warning(f"Could not build request for {s} with query '{q}'")
                    except Exception as e:
                        logging.error(f"Error building request for {s} with query '{q}': {str(e)}")
            
            if not tasks:
                logging.error("No valid API requests could be built")
                return []
            
            # Run tasks concurrently and collect results
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            
            for response in responses:
                if isinstance(response, Exception):
                    logging.error(f"Task raised exception: {str(response)}")
                    errors.append(str(response))
                    continue
                
                # Make sure response is a tuple with the expected elements
                if not isinstance(response, tuple) or len(response) != 3:
                    logging.error(f"Unexpected response format: {response}")
                    continue
                    
                # Unpack the response
                source, query, data = response
                
                if data is None:
                    logging.warning(f"No valid data from {source} for query '{query}'")
                    continue
                
                try:
                    # Process the data based on source type
                    if isinstance(data, list):
                        logging.info(f"Adding {len(data)} results from {source}")
                        # Process list items to ensure they have necessary fields
                        for item in data:
                            if isinstance(item, dict):
                                # Ensure basic required fields
                                if 'id' not in item:
                                    item['id'] = f"{source}_{hash(str(item))}"
                                if 'url' not in item:
                                    if 'urls' in item and isinstance(item['urls'], dict) and 'regular' in item['urls']:
                                        item['url'] = item['urls']['regular']
                                if 'thumbnail_url' not in item:
                                    if 'urls' in item and isinstance(item['urls'], dict) and 'thumb' in item['urls']:
                                        item['thumbnail_url'] = item['urls']['thumb']
                                results.append(item)
                    elif isinstance(data, dict) and "results" in data:
                        logging.info(f"Adding {len(data['results'])} results from {source}")
                        # Process each result
                        for item in data['results']:
                            if isinstance(item, dict):
                                # Ensure basic required fields
                                if 'id' not in item:
                                    item['id'] = f"{source}_{hash(str(item))}"
                                if 'source' not in item:
                                    item['source'] = source
                                results.append(item)
                    elif isinstance(data, dict) and "hits" in data:  # Pixabay specific
                        logging.info(f"Adding {len(data['hits'])} results from {source}")
                        # Process each hit from Pixabay
                        for item in data['hits']:
                            if isinstance(item, dict):
                                # Transform Pixabay format to match our expected format
                                processed_item = {
                                    'id': item.get('id', f"pixabay_{hash(str(item))}"),
                                    'url': item.get('largeImageURL', item.get('webformatURL', '')),
                                    'thumbnail_url': item.get('previewURL', ''),
                                    'description': item.get('tags', ''),
                                    'author': item.get('user', 'Unknown'),
                                    'source': 'pixabay',
                                    'width': item.get('imageWidth', 0),
                                    'height': item.get('imageHeight', 0),
                                    'tags': item.get('tags', '').split(', ')
                                }
                                results.append(processed_item)
                    elif isinstance(data, dict) and "photos" in data:  # Pexels specific
                        logging.info(f"Adding {len(data['photos'])} results from {source}")
                        # Process each photo from Pexels
                        for item in data['photos']:
                            if isinstance(item, dict):
                                # Transform Pexels format to match our expected format
                                processed_item = {
                                    'id': item.get('id', f"pexels_{hash(str(item))}"),
                                    'url': item.get('src', {}).get('large', ''),
                                    'thumbnail_url': item.get('src', {}).get('medium', ''),
                                    'description': item.get('alt', ''),
                                    'author': item.get('photographer', 'Unknown'),
                                    'source': 'pexels',
                                    'width': item.get('width', 0),
                                    'height': item.get('height', 0),
                                    'tags': []  # Pexels doesn't provide tags by default
                                }
                                results.append(processed_item)
                    else:
                        # Handle different response formats as needed
                        logging.debug(f"Unexpected response format from {source}: {type(data)}")
                        if isinstance(data, dict):
                            # Last resort, add the raw data with minimal processing
                            data['id'] = data.get('id', f"{source}_{hash(str(data))}")
                            data['source'] = source
                            results.append(data)
                except Exception as e:
                    error_details = traceback.format_exc()
                    logging.error(f"Error processing data from {source}: {str(e)}\n{error_details}")
    except Exception as e:
        error_details = traceback.format_exc()
        logging.error(f"Error in multi_source search: {str(e)}\n{error_details}")
    
    logging.info(f"Concurrent search completed with {len(results)} total results and {len(errors)} errors")
    return results