from flask import render_template, request, jsonify, redirect, url_for, flash, session
from app import app, db
from models import Image, Tag, Favorite, LibraryHelper
from NeedleRef.apis.unsplash_api import search_unsplash, get_image_details
from NeedleRef.apis.pexels_api import search_pexels, get_image_details as get_pexels_image_details
from NeedleRef.apis.pixabay_api import search_pixabay, get_image_details as get_pixabay_image_details
from NeedleRef.keyword_expander import expand
import logging
import requests
import random

# Import keyword expansion for local search
# Blueprint registration is done in main.py

@app.route('/')
def index():
    """Render the home page"""
    # Get all tags for filtering
    tags = Tag.query.order_by(Tag.category, Tag.name).all()

    # Organize tags by category
    tag_categories = {}
    for tag in tags:
        category = tag.category or 'Other'
        if category not in tag_categories:
            tag_categories[category] = []
        tag_categories[category].append(tag)

    return render_template('index.html', tag_categories=tag_categories)

@app.route('/search')
def search():
    """Handle image search requests"""
    # Get search parameters with validation
    query = request.args.get('query', '').strip()
    selected_tags = request.args.getlist('tags')

    try:
        page = max(1, int(request.args.get('page', 1)))  # Ensure page is at least 1
    except ValueError:
        page = 1

    source = request.args.get('source', 'all').lower()  # all, unsplash, pexels, or pixabay

    # Validate query
    if not query:
        return jsonify({'images': [], 'message': 'Please enter a search query'})

    # Set a reasonable per_page value
    per_page = 20

    try:
        all_results = []
        total_pages = 1
        sources_used = []
        api_errors = []

        # Search Unsplash if requested
        if source in ['all', 'unsplash']:
            try:
                unsplash_results = search_unsplash(query, per_page=per_page, page=page)
                unsplash_images = unsplash_results.get('results', [])
                if unsplash_images:
                    total_pages = max(total_pages, unsplash_results.get('total_pages', 0))
                    all_results.extend(unsplash_images)
                    sources_used.append('Unsplash')
                    logging.info(f"Found {len(unsplash_images)} images from Unsplash for query '{query}'")
            except Exception as e:
                error_msg = str(e)
                api_errors.append(f"Unsplash API error: {error_msg}")
                logging.error(f"Error searching Unsplash: {error_msg}")

        # Search Pexels if requested
        if source in ['all', 'pexels']:
            try:
                pexels_results = search_pexels(query, per_page=per_page, page=page)
                pexels_images = pexels_results.get('results', [])
                if pexels_images:
                    total_pages = max(total_pages, pexels_results.get('total_pages', 0))
                    all_results.extend(pexels_images)
                    sources_used.append('Pexels')
                    logging.info(f"Found {len(pexels_images)} images from Pexels for query '{query}'")
            except Exception as e:
                error_msg = str(e)
                api_errors.append(f"Pexels API error: {error_msg}")
                logging.error(f"Error searching Pexels: {error_msg}")
                
        # Search Pixabay if requested
        if source in ['all', 'pixabay']:
            try:
                pixabay_results = search_pixabay(query, per_page=per_page, page=page)
                pixabay_images = pixabay_results.get('results', [])
                if pixabay_images:
                    total_pages = max(total_pages, pixabay_results.get('total_pages', 0))
                    all_results.extend(pixabay_images)
                    sources_used.append('Pixabay')
                    logging.info(f"Found {len(pixabay_images)} images from Pixabay for query '{query}'")
            except Exception as e:
                error_msg = str(e)
                api_errors.append(f"Pixabay API error: {error_msg}")
                logging.error(f"Error searching Pixabay: {error_msg}")

        # If no results were found in any source
        if not all_results:
            message = "No images found for your search"
            if api_errors:
                message += f". API errors: {', '.join(api_errors)}"
            return jsonify({
                'images': [],
                'message': message,
                'error': bool(api_errors)
            })

        # Process and save images to database
        saved_images = []

        # Process images in smaller batches
        batch_size = 10
        for i in range(0, len(all_results), batch_size):
            batch = all_results[i:i + batch_size]

            try:
                with db.session.begin():
                    for image_data in batch:
                        try:
                            # Check image source
                            source = image_data.get('source', 'unsplash')
                            is_pexels = source == 'pexels'
                            is_pixabay = source == 'pixabay'
                            image_id = str(image_data['id'])  # Ensure ID is a string

                            # Look up existing image using unsplash_id outside transaction
                            existing_image = Image.query.filter_by(unsplash_id=image_id).first()

                            if existing_image:
                                # Use existing image
                                image = existing_image
                            else:
                                # Create new image entry with proper error handling for missing fields
                                try:
                                    # Handle different API sources with different data structures
                                    if is_pexels:
                                        # Pexels image structure
                                        image = Image(
                                            unsplash_id=image_id,
                                            description=image_data.get('alt', '') or image_data.get('description', '') or '',
                                            url=image_data.get('urls', {}).get('regular', ''),
                                            thumbnail_url=image_data.get('urls', {}).get('thumb', ''),
                                            width=image_data.get('width', 0),
                                            height=image_data.get('height', 0),
                                            author=image_data.get('user', {}).get('name', '') or image_data.get('photographer', ''),
                                            author_username=image_data.get('user', {}).get('username', '') or str(image_data.get('photographer_id', ''))
                                        )
                                    elif is_pixabay:
                                        # Pixabay image structure
                                        image = Image(
                                            unsplash_id=image_id,
                                            description=image_data.get('description', '') or '',
                                            url=image_data.get('url', ''),
                                            thumbnail_url=image_data.get('thumbnail_url', ''),
                                            width=image_data.get('width', 0),
                                            height=image_data.get('height', 0),
                                            author=image_data.get('author', ''),
                                            author_username=image_data.get('author_username', '')
                                        )
                                    else:
                                        # Unsplash image structure (default)
                                        image = Image(
                                            unsplash_id=image_id,
                                            description=image_data.get('description', '') or image_data.get('alt_description', '') or '',
                                            url=image_data.get('urls', {}).get('regular', ''),
                                            thumbnail_url=image_data.get('urls', {}).get('thumb', ''),
                                            width=image_data.get('width', 0),
                                            height=image_data.get('height', 0),
                                            author=image_data.get('user', {}).get('name', ''),
                                            author_username=image_data.get('user', {}).get('username', '')
                                        )

                                    # Extract and add tags
                                    if image_data.get('tags'):
                                        for tag_data in image_data['tags']:
                                            tag_name = tag_data.get('title', '').lower()
                                            if tag_name:
                                                # Find or create tag efficiently
                                                tag = Tag.query.filter_by(name=tag_name).first()
                                                if not tag:
                                                    # Try to determine category
                                                    category = 'Other'
                                                    if any(emotion in tag_name for emotion in ['happy', 'sad', 'angry', 'fear', 'surprise']):
                                                        category = 'Emotion'
                                                    elif any(angle in tag_name for angle in ['front', 'side', 'back', 'top', 'bottom']):
                                                        category = 'Angle'
                                                    else:
                                                        category = 'Subject'

                                                    tag = Tag(name=tag_name, category=category)
                                                    db.session.add(tag)

                                                # Add tag to image if not already present
                                                if tag not in image.tags:
                                                    image.tags.append(tag)

                                    # Add source tag
                                    if is_pexels:
                                        source_tag_name = 'pexels'
                                    elif is_pixabay:
                                        source_tag_name = 'pixabay'
                                    else:
                                        source_tag_name = 'unsplash'
                                        
                                    source_tag = Tag.query.filter_by(name=source_tag_name).first()
                                    if not source_tag:
                                        source_tag = Tag(name=source_tag_name, category='Source')
                                        db.session.add(source_tag)

                                    # Add source tag if not already present
                                    if source_tag not in image.tags:
                                        image.tags.append(source_tag)

                                    db.session.add(image)

                                except KeyError as ke:
                                    # Log and skip images with missing required fields
                                    logging.error(f"Skipping image due to missing field: {ke}")
                                    continue

                            # Check if image is favorited
                            is_favorite = Favorite.query.filter_by(image_id=image.id).first() is not None

                            # Prepare image data for response
                            image_dict = image.to_dict()
                            image_dict['is_favorite'] = is_favorite
                            saved_images.append(image_dict)

                        except Exception as img_error:
                            # Log error and continue with next image
                            logging.error(f"Error processing image: {str(img_error)}")
                            continue

                # Commit each batch
                db.session.commit()
            except Exception as batch_error:
                db.session.rollback()
                logging.error(f"Error processing batch: {str(batch_error)}")
                continue

        # Filter by tags if selected
        if selected_tags:
            filtered_images = []
            keywords = query.lower().split()
            for image in saved_images:
                # Calculate relevance score
                score = 0

                # Primary relevance from tags
                if any(tag in image['tags'] for tag in selected_tags):
                    score += 1.0

                # Check weights (highest priority)
                weights = image.get("weights") or {}
                for key, weight in weights.items():
                    if key and any(word.lower() in key.lower() for word in keywords):
                        score += weight * 2

                # Fallback to description text (lower priority)
                description = image.get('description', '').lower()
                if query in description:
                    score += 0.2

                if score > 0:
                    image['relevance_score'] = score
                    filtered_images.append(image)

            saved_images = filtered_images

        # Sort images by relevance score
        sorted_images = sorted(saved_images, 
                                 key=lambda x: x.get('relevance_score', 1.0),
                                 reverse=True)

        # Return the search results with metadata
        return jsonify({
            'images': sorted_images,
            'page': page,
            'total_pages': total_pages,
            'has_more': page < total_pages,
            'sources': sources_used,
            'query': query
        })

    except requests.RequestException as e:
        db.session.rollback()
        logging.error(f"API request error: {str(e)}", exc_info=True)
        return jsonify({
            'error': True,
            'message': 'Failed to connect to image service. Please try again.'
        }), 503
    except ValueError as e:
        db.session.rollback()
        logging.error(f"Validation error: {str(e)}", exc_info=True)
        return jsonify({
            'error': True,
            'message': 'Invalid search parameters provided.'
        }), 400
    except Exception as e:
        db.session.rollback()
        logging.error(f"Unexpected error: {str(e)}", exc_info=True)
        return jsonify({
            'error': True,
            'message': 'An unexpected error occurred. Please try again.'
        }), 500

@app.route('/favorites')
def favorites():
    """Display user's favorite images"""
    return render_template('favorites.html')

@app.route('/api/favorites')
def get_favorites():
    """API endpoint to get favorite images"""
    favorites = Favorite.query.order_by(Favorite.date_added.desc()).all()
    favorite_images = [fav.image.to_dict() for fav in favorites]
    return jsonify({'images': favorite_images})

@app.route('/api/favorites/add/<int:image_id>', methods=['POST'])
def add_favorite(image_id):
    """Add an image to favorites"""
    image = Image.query.get_or_404(image_id)

    # Check if already a favorite
    existing = Favorite.query.filter_by(image_id=image_id).first()
    if existing:
        return jsonify({'message': 'Image already in favorites'})

    # Add to favorites
    favorite = Favorite(image_id=image_id)
    db.session.add(favorite)
    db.session.commit()

    return jsonify({'message': 'Added to favorites', 'image': image.to_dict()})

@app.route('/api/favorites/remove/<int:image_id>', methods=['POST'])
def remove_favorite(image_id):
    """Remove an image from favorites"""
    favorite = Favorite.query.filter_by(image_id=image_id).first()

    if not favorite:
        return jsonify({'message': 'Image not in favorites'})

    db.session.delete(favorite)
    db.session.commit()

    return jsonify({'message': 'Removed from favorites', 'image_id': image_id})

@app.route('/api/tags')
def get_tags():
    """Get all available tags"""
    tags = Tag.query.all()
    return jsonify({'tags': [{'id': tag.id, 'name': tag.name, 'category': tag.category} for tag in tags]})

@app.route('/library')
def library():
    """Display user's local library images"""
    return render_template('library.html')

@app.route('/api/library')
def get_library():
    """API endpoint to get library images"""
    main_category = request.args.get('main_category')
    subcategory = request.args.get('subcategory')
    search_query = request.args.get('search', '').lower()

    library_images = LibraryHelper.get_all_library_images(main_category, subcategory)

    # Filter by search query if provided
    if search_query:
        filtered_images = []
        for image in library_images:
            tags = [tag.lower() for tag in image.get('tags', [])]
            if any(search_query in tag for tag in tags):
                filtered_images.append(image)
        library_images = filtered_images

    return jsonify({'images': library_images})

@app.route('/api/library/categories')
def get_library_categories():
    """Get all available categories for organization"""
    return jsonify(LibraryHelper.get_available_categories())

@app.route('/api/library/add-user-image', methods=['POST'])
def add_user_image():
    """Add a user-uploaded image to the library"""
    data = request.json
    if not data or 'image' not in data:
        return jsonify({"success": False, "message": "No image data provided"})

    try:
        # Create a unique ID for the image
        import uuid
        unique_id = f"user_{str(uuid.uuid4())}"

        # Create a temporary Image object
        temp_image = Image(
            unsplash_id=unique_id,
            description=data.get('description', 'User uploaded image'),
            url=data['image'],
            thumbnail_url=data['image'],
            width=0,
            height=0,
            author='User',
            author_username='user'
        )
        
        # Add to library
        result = LibraryHelper.add_to_library(temp_image, data.get('main_category'), data.get('subcategory'))

        return jsonify(result)

    except Exception as e:
        logging.error(f"Error saving user image: {str(e)}")
        return jsonify({
            "success": False,
            "message": "Failed to save image to library"
        })

@app.route('/api/library/stats')
def get_library_stats():
    """Get statistics about the library categories"""
    return jsonify(LibraryHelper.get_category_stats())

@app.route('/api/library/add/<int:image_id>', methods=['POST'])
def add_to_library(image_id):
    """Add an image to the local SQLite library"""
    image = Image.query.get_or_404(image_id)

    # Save to SQLite library
    result = LibraryHelper.add_to_library(image)

    # Check if we need to include additional information for the UI
    if result.get('success'):
        # Include main category and subcategory information
        result['main_category'] = result.get('main_category', '')
        result['subcategory'] = result.get('subcategory', '')
        # If this is a new category/subcategory, mark it
        result['new_category'] = result.get('new_category', False)

    return jsonify(result)

@app.route('/api/library/remove/<int:library_id>', methods=['POST'])
def remove_from_library(library_id):
    """Remove an image from the local SQLite library"""
    result = LibraryHelper.delete_from_library(library_id)
    return jsonify(result)

@app.route('/api/library/tags/<int:library_id>', methods=['GET'])
def get_library_tags(library_id):
    """Get tags for a library image"""
    tags = LibraryHelper.get_library_tags(library_id)
    return jsonify(tags)

@app.route('/api/library/tags/<int:library_id>', methods=['POST'])
def add_library_tags(library_id):
    """Add custom tags to a library image"""
    tags_string = request.json.get('tags', '')
    result = LibraryHelper.add_custom_tags(library_id, tags_string)
    return jsonify(result)

@app.route('/api/library/image/<int:library_id>', methods=['GET'])
def get_library_image(library_id):
    """Get a specific image from the library"""
    image = LibraryHelper.get_library_image(library_id)
    if not image:
        return jsonify({"error": "Image not found"}), 404
    return jsonify(image)

@app.route('/api/library/category/<int:library_id>', methods=['POST'])
def update_image_category(library_id):
    """Update the category for a library image"""
    data = request.json
    main_category = data.get('main_category')
    subcategory = data.get('subcategory')

    if not main_category or not subcategory:
        return jsonify({"success": False, "message": "Main category and subcategory are required"}), 400

    result = LibraryHelper.update_image_category(library_id, main_category, subcategory)
    return jsonify(result)

@app.route('/sketch')
def sketch_tool():
    """Render the sketch tool page"""
    image_url = request.args.get('image', '')
    return render_template('sketch.html', image_url=image_url)


# Enhanced in-memory cache for search results
# Structure: {query_hash: {'timestamp': time, 'results': data}}
SEARCH_CACHE = {}
CACHE_DURATION = 86400  # 24 hours in seconds
EXTENDED_CACHE_SIZE = 500  # Maximum number of cached searches

@app.route('/api/smartsearch')
def smart_search():
    import hashlib
    import time
    import logging
    from sqlalchemy import text
    
    query = request.args.get('query', '').lower().strip()
    use_cache = request.args.get('cache', 'true').lower() == 'true'
    use_expansion = request.args.get('expand', 'true').lower() == 'true'
    
    if not query:
        return jsonify({'results': [], 'message': 'No query provided'}), 400

    # Create a unique hash for this query (include expansion flag)
    query_key = f"{query}_{use_expansion}"
    query_hash = hashlib.md5(query_key.encode()).hexdigest()
    current_time = time.time()
    
    # Check cache if enabled
    if use_cache and query_hash in SEARCH_CACHE:
        cache_data = SEARCH_CACHE[query_hash]
        if current_time - cache_data['timestamp'] < CACHE_DURATION:
            logging.info(f"Cache hit for query: {query}")
            # Update the access time
            cache_data['accessed'] = current_time
            SEARCH_CACHE[query_hash] = cache_data
            return jsonify({
                'results': cache_data['results'], 
                'from_cache': True, 
                'cache_age': round((current_time - cache_data['timestamp']) / 60, 1),  # Age in minutes
                'expanded': cache_data.get('expanded', False)
            })
    
    # Expand the query using our keyword_expander if enabled
    expanded_queries = []
    if use_expansion:
        expanded_queries = expand(query)
        logging.info(f"Expanded query '{query}' to {len(expanded_queries)} variations")
    else:
        expanded_queries = [query]  # Just use the original query
    
    # First, try the PostgreSQL database with full-text search
    try:
        # Use all expanded queries for search
        all_keywords = []
        for expanded_query in expanded_queries:
            all_keywords.extend(expanded_query.split())
        
        # Remove duplicates while preserving order
        unique_keywords = []
        for kw in all_keywords:
            if kw not in unique_keywords:
                unique_keywords.append(kw)
                
        search_terms = ' | '.join(unique_keywords)  # OR search
        
        # Use proper parameterized SQL for security
        sql = text("""
            SELECT i.*, 
                ts_rank_cd(to_tsvector('english', COALESCE(i.description, '')), 
                          to_tsquery('english', :search_terms)) AS rank
            FROM image i
            LEFT JOIN image_tags it ON i.id = it.image_id
            LEFT JOIN tag t ON it.tag_id = t.id
            WHERE to_tsvector('english', COALESCE(i.description, '')) @@ to_tsquery('english', :search_terms)
               OR LOWER(t.name) LIKE ANY(ARRAY[:tag_terms])
            GROUP BY i.id
            ORDER BY rank DESC
            LIMIT 50
        """)
        
        # Prepare tag search terms with wildcards
        tag_terms = [f"%{kw}%" for kw in unique_keywords]
        
        # Execute query
        result = db.session.execute(sql, {'search_terms': search_terms, 'tag_terms': tag_terms})
        rows = result.fetchall()
        
        # Process results
        db_images = []
        for row in rows:
            image = Image.query.get(row[0])  # Get full image object
            if image:
                image_dict = image.to_dict()
                image_dict['rank'] = float(row[-1])  # Add rank score
                db_images.append(image_dict)
        
        # If postgres search returned results, use those directly
        if db_images:
            logging.info(f"PostgreSQL fulltext search found {len(db_images)} results for '{query}'")
            
            # Update cache with LRU management
            if use_cache:
                # Remove oldest items if cache exceeds size limit
                if len(SEARCH_CACHE) >= EXTENDED_CACHE_SIZE:
                    oldest_query = None
                    oldest_time = float('inf')
                    for qh, data in SEARCH_CACHE.items():
                        if data['timestamp'] < oldest_time:
                            oldest_time = data['timestamp']
                            oldest_query = qh
                    if oldest_query:
                        logging.debug(f"Evicting oldest cache entry to stay within size limits")
                        SEARCH_CACHE.pop(oldest_query, None)
                        
                # Add current query to cache
                SEARCH_CACHE[query_hash] = {
                    'timestamp': current_time, 
                    'results': db_images,
                    'accessed': current_time,  # Track last access time
                    'expanded': use_expansion  # Track if this result used expansion
                }
                
            return jsonify({
                'results': db_images,
                'expanded': use_expansion,
                'expanded_terms': expanded_queries if use_expansion else [query]
            })
    
    except Exception as e:
        logging.error(f"PostgreSQL fulltext search error: {str(e)}")
        # Continue to fallback implementation
    
    # Fallback: Enhanced library search with weighted scores
    try:
        # Define your smart tag buckets
        KNOWN_SUBJECTS = {"dog", "cat", "skull", "rose", "dragon", "snake", "butterfly", "koi", "wolf"}
        KNOWN_STYLES = {"blackwork", "fine line", "dotwork", "drawing", "realism", "line art", "sketch"}
        KNOWN_TECHNIQUES = {"shading", "stippling", "crosshatching", "stencil", "engraving"}
        
        # Add more terms than before
        for art_style in ["traditional", "neo-traditional", "japanese", "geometric", "watercolor"]:
            KNOWN_STYLES.add(art_style)
            
        for subject in ["flower", "bird", "tree", "mountain", "animal", "fish", "lotus", "moon", "sun", "star"]:
            KNOWN_SUBJECTS.add(subject)
        
        # Process all keywords from expanded queries if expansion is enabled
        all_keywords = []
        if use_expansion:
            # We're already using expanded queries from above
            for expanded_query in expanded_queries:
                all_keywords.extend(expanded_query.split())
            # Remove duplicates but preserve order
            keywords = []
            for kw in all_keywords:
                if kw not in keywords:
                    keywords.append(kw)
            logging.info(f"Using {len(keywords)} expanded keywords for library search")
        else:
            keywords = query.split()
            
        results = []
        
        # Get images from your local library
        logging.info(f"Falling back to library search for '{query}'")
        library_images = LibraryHelper.get_all_library_images(None, None)
        
        # For each image, calculate relevance score with more sophisticated weighting
        for image in library_images:
            score = 0
            weights = image.get('weights', {}) or {}
            description = (image.get('description', '') or '').lower()
            tags = [t.lower() for t in image.get('tags', [])]
            
            # Check exact query match first (highest priority)
            if query in description:
                score += 3.0
                
            # Check tags for direct matches
            if any(query in tag for tag in tags):
                score += 2.5
                
            # Process individual keywords
            for word in keywords:
                matched = False
                
                # Match weights dictionary (structured data is highest quality)
                if word in KNOWN_SUBJECTS:
                    key = f"subject.{word}"
                    if key in weights:
                        score += weights[key] * 3
                        matched = True
                
                if word in KNOWN_STYLES:
                    key = f"style.{word}"
                    if key in weights:
                        score += weights[key] * 2
                        matched = True
                
                if word in KNOWN_TECHNIQUES:
                    key = f"technique.{word}"
                    if key in weights:
                        score += weights[key] * 1.5
                        matched = True
                
                # Check tags (second priority)
                if not matched and any(word in tag for tag in tags):
                    score += 1.0
                    matched = True
                    
                # Fallback: description keyword match (lowest priority)
                if not matched and word in description:
                    score += 0.2
            
            if score > 0:
                image['relevance_score'] = score
                results.append((score, image))
        
        # Sort and deduplicate
        results.sort(key=lambda x: x[0], reverse=True)
        seen = set()
        unique_images = []
        
        for _, img in results:
            img_id = img.get('id') or img.get('image_id') or img.get('url')
            if img_id not in seen:
                seen.add(img_id)
                unique_images.append(img)
            if len(unique_images) >= 50:  # Increased limit
                break
        
        # Update cache with results using the same LRU management
        if use_cache:
            # Remove oldest items if cache exceeds size limit
            if len(SEARCH_CACHE) >= EXTENDED_CACHE_SIZE:
                oldest_query = None
                oldest_time = float('inf')
                for qh, data in SEARCH_CACHE.items():
                    if data['timestamp'] < oldest_time:
                        oldest_time = data['timestamp']
                        oldest_query = qh
                if oldest_query:
                    logging.debug(f"Evicting oldest cache entry to stay within size limits")
                    SEARCH_CACHE.pop(oldest_query, None)
                    
            # Add current query to cache
            SEARCH_CACHE[query_hash] = {
                'timestamp': current_time, 
                'results': unique_images,
                'accessed': current_time,  # Track last access time
                'expanded': use_expansion  # Track if this result used expansion
            }
        
        return jsonify({
            'results': unique_images,
            'expanded': use_expansion,
            'expanded_terms': expanded_queries if use_expansion else [query]
        })
        
    except Exception as e:
        logging.error(f"Library smart search error: {str(e)}")
        return jsonify({
            'error': True,
            'message': f'Search error: {str(e)}',
            'results': []
        }), 500


@app.route('/api/search/suggest')
def search_suggestions():
    """Provide fast search term suggestions based on partial queries"""
    import re
    import time
    import logging
    from collections import Counter
    
    # Get the partial query from request
    partial = request.args.get('query', '').lower().strip()
    
    if not partial or len(partial) < 2:
        return jsonify({'suggestions': []})
    
    try:
        # Check tag database for matching terms
        tags = Tag.query.filter(Tag.name.ilike(f"%{partial}%")).order_by(Tag.name).limit(10).all()
        tag_suggestions = [tag.name for tag in tags]
        
        # Get common words from image descriptions
        common_words = []
        
        # Use the faster SQL query with LIMIT to avoid scanning the entire table
        sql = """
            SELECT description FROM image 
            WHERE description ILIKE :pattern
            LIMIT 50
        """
        
        result = db.session.execute(sql, {"pattern": f"%{partial}%"})
        descriptions = [row[0] for row in result if row[0]]
        
        # Extract words from descriptions
        word_pattern = re.compile(r'\b\w+\b')
        words = []
        
        for desc in descriptions:
            if desc:
                matches = word_pattern.findall(desc.lower())
                words.extend([w for w in matches if partial in w.lower() and len(w) >= 3])
        
        # Count occurrences and get most common
        word_counter = Counter(words)
        common_words = [word for word, count in word_counter.most_common(5)]
        
        # Combine all suggestions, remove duplicates, and sort
        all_suggestions = list(set(tag_suggestions + common_words))
        all_suggestions.sort(key=lambda x: (0 if x.lower().startswith(partial) else 1, len(x)))
        
        # Limit to top 10
        suggestions = all_suggestions[:10]
        
        return jsonify({
            'suggestions': suggestions
        })
        
    except Exception as e:
        logging.error(f"Error generating search suggestions: {str(e)}")
        return jsonify({
            'error': True,
            'message': f'Error generating suggestions: {str(e)}',
            'suggestions': []
        }), 500