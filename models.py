from app import db
from datetime import datetime
import os
import sqlite3

# Association table for many-to-many relationship between images and tags
image_tags = db.Table('image_tags',
    db.Column('image_id', db.Integer, db.ForeignKey('image.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id'), primary_key=True)
)

# Create a SQLite connection for the Library model (separate from PostgreSQL)
SQLITE_DB_PATH = 'instance/tattoo_reference.db'
os.makedirs(os.path.dirname(SQLITE_DB_PATH), exist_ok=True)

# Predefined categories for tattoo references
TATTOO_CATEGORIES = {
    "Anatomy & Body Parts": [
        "Faces", "Front", "Side", "¾ Angle", "Expressions",
        "Hands", "Gestures", "Grips", "Poses",
        "Arms & Legs", "Torsos & Backs", "Feet", "Skulls"
    ],
    "Nature": [
        "Flowers", "Roses", "Peonies", "Lotuses", "Wildflowers",
        "Plants & Leaves", "Animals", "Snakes", "Birds", "Wolves",
        "Big Cats", "Insects", "Natural Scenes"
    ],
    "Myth & Fantasy": [
        "Dragons", "Demons", "Gods/Goddesses", "Mythical Creatures", "Angels & Wings"
    ],
    "Objects": [
        "Daggers", "Clocks", "Jewelry", "Weapons", "Sacred Geometry", "Crystals"
    ],
    "Symbolism & Spiritual": [
        "Eyes", "Hands of Fatima", "Tarot-inspired", "Mandalas", "Religious Symbols"
    ],
    "Style-Based": [
        "Traditional", "Neo-Traditional", "Blackwork", "Realism", 
        "Dotwork", "Minimalist", "Surreal"
    ],
    "My References": [
        "Uploaded Images", "Sketches", "Reference Photos"
    ]
}

# Flattened list of all subcategories
ALL_SUBCATEGORIES = []
for main_category, subcategories in TATTOO_CATEGORIES.items():
    for subcategory in subcategories:
        ALL_SUBCATEGORIES.append(subcategory)

# Create and update the library table in SQLite
def update_sqlite_db():
    """Initialize or update the SQLite database schema"""
    import logging
    logging.info("Initializing/updating SQLite database schema")
    conn = sqlite3.connect(SQLITE_DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check if library table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='library'")
        library_exists = cursor.fetchone() is not None
        
        if not library_exists:
            logging.info("Creating library table")
            # Create library table with category fields
            cursor.execute('''
            CREATE TABLE library (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                unsplash_id TEXT NOT NULL UNIQUE,
                description TEXT,
                url TEXT NOT NULL,
                thumbnail_url TEXT NOT NULL,
                width INTEGER NOT NULL,
                height INTEGER NOT NULL,
                author TEXT,
                author_username TEXT,
                main_category TEXT,
                subcategory TEXT,
                date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            # Create library_tags table
            cursor.execute('''
            CREATE TABLE library_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                library_id INTEGER,
                tag_name TEXT NOT NULL,
                is_custom INTEGER DEFAULT 0, -- 0 = imported tag, 1 = custom user tag
                FOREIGN KEY (library_id) REFERENCES library (id) ON DELETE CASCADE
            )
            ''')
        else:
            # Check if we need to add the category columns
            cursor.execute("PRAGMA table_info(library)")
            columns = cursor.fetchall()
            column_names = [col[1] for col in columns]
            
            if 'main_category' not in column_names:
                logging.info("Adding main_category column to library table")
                cursor.execute("ALTER TABLE library ADD COLUMN main_category TEXT")
            
            if 'subcategory' not in column_names:
                logging.info("Adding subcategory column to library table")
                cursor.execute("ALTER TABLE library ADD COLUMN subcategory TEXT")
            
            # Check if library_tags table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='library_tags'")
            tags_exists = cursor.fetchone() is not None
            
            if not tags_exists:
                logging.info("Creating library_tags table")
                cursor.execute('''
                CREATE TABLE library_tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    library_id INTEGER,
                    tag_name TEXT NOT NULL,
                    is_custom INTEGER DEFAULT 0,
                    FOREIGN KEY (library_id) REFERENCES library (id) ON DELETE CASCADE
                )
                ''')
            else:
                # Check if we need to add the is_custom column to library_tags
                cursor.execute("PRAGMA table_info(library_tags)")
                tag_columns = cursor.fetchall()
                tag_column_names = [col[1] for col in tag_columns]
                
                if 'is_custom' not in tag_column_names:
                    logging.info("Adding is_custom column to library_tags table")
                    cursor.execute("ALTER TABLE library_tags ADD COLUMN is_custom INTEGER DEFAULT 0")
        
        conn.commit()
        logging.info("SQLite database schema initialized/updated successfully")
        
    except sqlite3.Error as e:
        conn.rollback()
        logging.error(f"Error initializing/updating SQLite database: {str(e)}")
        
    finally:
        conn.close()

# Initialize SQLite database
update_sqlite_db()

class Image(db.Model):
    """Model for storing image metadata from Unsplash"""
    id = db.Column(db.Integer, primary_key=True)
    unsplash_id = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    url = db.Column(db.String(255), nullable=False)
    thumbnail_url = db.Column(db.String(255), nullable=False)
    width = db.Column(db.Integer, nullable=False)
    height = db.Column(db.Integer, nullable=False) 
    author = db.Column(db.String(100), nullable=True)
    author_username = db.Column(db.String(100), nullable=True)
    date_added = db.Column(db.DateTime, default=datetime.utcnow)
    weights = db.Column(db.JSON, nullable=True)  # Store weights as native JSON
    
    # Relationships
    tags = db.relationship('Tag', secondary=image_tags, backref=db.backref('images', lazy='dynamic'))
    favorites = db.relationship('Favorite', backref='image', lazy='dynamic', cascade="all, delete-orphan")
    
    def to_dict(self):
        """Convert image to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'unsplash_id': self.unsplash_id,
            'description': self.description,
            'url': self.url,
            'thumbnail_url': self.thumbnail_url,
            'width': self.width,
            'height': self.height,
            'author': self.author,
            'author_username': self.author_username,
            'tags': [tag.name for tag in self.tags],
            'date_added': self.date_added.isoformat() if self.date_added else None,
            'is_favorite': len(self.favorites.all()) > 0
        }

class Tag(db.Model):
    """Model for tags associated with images"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    category = db.Column(db.String(50), nullable=True)  # emotion, subject, angle, etc.
    
    def __repr__(self):
        return f'<Tag {self.name}>'

class Favorite(db.Model):
    """Model for user's favorite images"""
    id = db.Column(db.Integer, primary_key=True)
    image_id = db.Column(db.Integer, db.ForeignKey('image.id'), nullable=False)
    date_added = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Favorite {self.id}>'


# This section was removed to fix the duplicate function issue


# SQLite Library Helper Functions
class LibraryHelper:
    @staticmethod
    def add_to_library(image, main_category=None, subcategory=None):
        """Add an image to the SQLite library
        
        Args:
            image: The image object from PostgreSQL
            main_category (str, optional): The main category for organization
            subcategory (str, optional): The subcategory for organization
        """
        import logging
        logging.debug(f"Adding image to library: {image.id} (Unsplash ID: {image.unsplash_id})")
        
        conn = sqlite3.connect(SQLITE_DB_PATH)
        cursor = conn.cursor()
        
        try:
            # Check if the image already exists in the library
            cursor.execute('SELECT id FROM library WHERE unsplash_id = ?', (image.unsplash_id,))
            existing = cursor.fetchone()
            
            if existing:
                # Image already in library
                logging.debug(f"Image already in library with ID: {existing[0]}")
                return {"success": False, "message": "Image already in library", "existing_id": existing[0]}
            
            # Try to auto-categorize based on tags if no category provided
            if not main_category or not subcategory:
                auto_categorized = LibraryHelper.auto_categorize_image(image.tags)
                main_category = main_category or auto_categorized.get('main_category')
                subcategory = subcategory or auto_categorized.get('subcategory')
                logging.debug(f"Auto-categorized image as: {main_category}/{subcategory}")
                
                # If we still couldn't determine a category, use "Uncategorized"
                if not main_category:
                    main_category = "Uncategorized"
                if not subcategory:
                    subcategory = "Uncategorized"
                logging.debug(f"Final category assignment: {main_category}/{subcategory}")
            
            # Check if this category/subcategory combination is new
            cursor.execute(
                'SELECT COUNT(*) FROM library WHERE main_category = ? AND subcategory = ?',
                (main_category, subcategory)
            )
            category_count = cursor.fetchone()[0]
            is_new_category = category_count == 0
            logging.debug(f"Is new category/subcategory combination: {is_new_category}")
            
            # Insert image into library with categories
            logging.debug(f"Inserting image into library with categories: {main_category}/{subcategory}")
            cursor.execute('''
            INSERT INTO library (
                unsplash_id, description, url, thumbnail_url, 
                width, height, author, author_username,
                main_category, subcategory
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                image.unsplash_id,
                image.description,
                image.url,
                image.thumbnail_url,
                image.width,
                image.height,
                image.author,
                image.author_username,
                main_category,
                subcategory
            ))
            
            # Get the newly inserted library_id
            library_id = cursor.lastrowid
            logging.debug(f"New library ID: {library_id}")
            
            # Insert tags for the image
            tag_count = 0
            for tag in image.tags:
                cursor.execute('INSERT INTO library_tags (library_id, tag_name) VALUES (?, ?)',
                              (library_id, tag.name))
                tag_count += 1
            
            logging.debug(f"Added {tag_count} tags to the image")
            conn.commit()
            logging.debug("Successfully saved image to library")
            
            return {
                "success": True, 
                "message": "Image saved to library", 
                "library_id": library_id,
                "main_category": main_category,
                "subcategory": subcategory,
                "new_category": is_new_category
            }
        
        except sqlite3.Error as e:
            conn.rollback()
            logging.error(f"SQLite error when saving to library: {str(e)}")
            return {"success": False, "message": f"Error saving to library: {str(e)}"}
        
        except Exception as e:
            conn.rollback()
            logging.error(f"Unexpected error when saving to library: {str(e)}", exc_info=True)
            return {"success": False, "message": f"Unexpected error: {str(e)}"}
        
        finally:
            conn.close()
    
    @staticmethod
    def auto_categorize_image(tags):
        """Attempt to automatically categorize an image based on its tags
        
        Args:
            tags: List of Tag objects or tag names
            
        Returns:
            dict: Suggested main_category and subcategory
        """
        # Convert Tag objects to tag names if needed
        tag_names = []
        for tag in tags:
            if hasattr(tag, 'name'):
                tag_names.append(tag.name.lower())
            else:
                tag_names.append(str(tag).lower())
        
        # Map of keywords to subcategories
        keyword_to_subcategory = {
            # Anatomy
            "face": "Faces",
            "portrait": "Faces",
            "hand": "Hands",
            "finger": "Hands",
            "arm": "Arms & Legs",
            "leg": "Arms & Legs",
            "foot": "Feet",
            "feet": "Feet",
            "skull": "Skulls",
            "bone": "Skulls",
            "torso": "Torsos & Backs",
            "back": "Torsos & Backs",
            
            # Nature
            "flower": "Flowers",
            "rose": "Roses",
            "peony": "Peonies",
            "lotus": "Lotuses",
            "plant": "Plants & Leaves",
            "leaf": "Plants & Leaves",
            "leaves": "Plants & Leaves",
            "animal": "Animals",
            "snake": "Snakes",
            "serpent": "Snakes",
            "bird": "Birds",
            "wolf": "Wolves",
            "lion": "Big Cats",
            "tiger": "Big Cats",
            "cat": "Big Cats",
            "insect": "Insects",
            "bug": "Insects",
            "butterfly": "Insects",
            "mountain": "Natural Scenes",
            "ocean": "Natural Scenes",
            "wave": "Natural Scenes",
            "tree": "Natural Scenes",
            
            # Myth & Fantasy
            "dragon": "Dragons",
            "demon": "Demons",
            "devil": "Demons",
            "god": "Gods/Goddesses",
            "goddess": "Gods/Goddesses",
            "deity": "Gods/Goddesses",
            "mythical": "Mythical Creatures",
            "fantasy": "Mythical Creatures",
            "angel": "Angels & Wings",
            "wing": "Angels & Wings",
            
            # Objects
            "dagger": "Daggers",
            "knife": "Daggers",
            "clock": "Clocks",
            "time": "Clocks",
            "jewelry": "Jewelry",
            "ring": "Jewelry",
            "necklace": "Jewelry",
            "weapon": "Weapons",
            "sword": "Weapons",
            "gun": "Weapons",
            "sacred geometry": "Sacred Geometry",
            "geometric": "Sacred Geometry",
            "crystal": "Crystals",
            "gem": "Crystals",
            
            # Symbolism & Spiritual
            "eye": "Eyes",
            "hamsa": "Hands of Fatima",
            "fatima": "Hands of Fatima",
            "tarot": "Tarot-inspired",
            "card": "Tarot-inspired",
            "mandala": "Mandalas",
            "religious": "Religious Symbols",
            "cross": "Religious Symbols",
            
            # Style-Based
            "traditional": "Traditional",
            "old school": "Traditional",
            "neo-traditional": "Neo-Traditional",
            "blackwork": "Blackwork",
            "realistic": "Realism",
            "realism": "Realism",
            "dotwork": "Dotwork",
            "minimal": "Minimalist",
            "minimalist": "Minimalist",
            "surreal": "Surreal",
            "abstract": "Surreal"
        }
        
        # Map of subcategories to main categories
        subcategory_to_main = {}
        for main_cat, subcats in TATTOO_CATEGORIES.items():
            for subcat in subcats:
                subcategory_to_main[subcat] = main_cat
        
        # Check for keyword matches in tags
        matched_subcategories = {}
        
        for tag in tag_names:
            for keyword, subcategory in keyword_to_subcategory.items():
                if keyword in tag:
                    matched_subcategories[subcategory] = matched_subcategories.get(subcategory, 0) + 1
        
        # Find the most common subcategory
        best_subcategory = None
        highest_count = 0
        
        for subcategory, count in matched_subcategories.items():
            if count > highest_count:
                highest_count = count
                best_subcategory = subcategory
        
        # Get the main category for this subcategory
        main_category = None
        if best_subcategory:
            main_category = subcategory_to_main.get(best_subcategory)
        
        return {
            "main_category": main_category,
            "subcategory": best_subcategory
        }
    
    @staticmethod
    def get_all_library_images(main_category=None, subcategory=None):
        """Get all images from the library, optionally filtered by category
        
        Args:
            main_category (str, optional): Filter by main category
            subcategory (str, optional): Filter by subcategory
            
        Returns:
            list: Images matching the criteria
        """
        import logging
        logging.debug(f"Getting library images (filters: main_category={main_category}, subcategory={subcategory})")
        
        conn = sqlite3.connect(SQLITE_DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            # Build the query based on filters
            query = 'SELECT * FROM library'
            params = []
            
            # Add category filters if provided
            where_clauses = []
            if main_category:
                where_clauses.append('main_category = ?')
                params.append(main_category)
            
            if subcategory:
                where_clauses.append('subcategory = ?')
                params.append(subcategory)
            
            # Add WHERE clause if we have filters
            if where_clauses:
                query += ' WHERE ' + ' AND '.join(where_clauses)
            
            # Add ORDER BY
            query += ' ORDER BY date_added DESC'
            
            logging.debug(f"Executing query: {query} with params: {params}")
            
            # Execute the query
            cursor.execute(query, params)
            images = cursor.fetchall()
            logging.debug(f"Found {len(images)} images in library")
            
            # Check if we can see the structure of the first image
            if images and len(images) > 0:
                sample_img = images[0]
                logging.debug(f"Sample image data: {dict(sample_img)}")
                
            result = []
            for img in images:
                # Get tags for this image
                cursor.execute('SELECT tag_name FROM library_tags WHERE library_id = ?', (img['id'],))
                tags = [row['tag_name'] for row in cursor.fetchall()]
                
                # Convert to dictionary
                image_dict = dict(img)
                image_dict['tags'] = tags
                result.append(image_dict)
            
            logging.debug(f"Returning {len(result)} processed images")
            return result
        
        except sqlite3.Error as e:
            logging.error(f"SQLite error getting library images: {str(e)}")
            return []
        
        except Exception as e:
            logging.error(f"Unexpected error getting library images: {str(e)}", exc_info=True)
            return []
        
        finally:
            conn.close()
    
    @staticmethod
    def get_category_stats():
        """Get statistics about categories in the library
        
        Returns:
            dict: Counts of images in each category and subcategory
        """
        conn = sqlite3.connect(SQLITE_DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            # Initialize category structure with all subcategories
            categories = {}
            for main_cat, subcats in TATTOO_CATEGORIES.items():
                categories[main_cat] = {
                    "count": 0,
                    "subcategories": {subcat: 0 for subcat in subcats}
                }
            
            # Add "Uncategorized" category
            categories["Uncategorized"] = {
                "count": 0,
                "subcategories": {"Uncategorized": 0}
            }
            
            # Get counts by main category
            cursor.execute('''
            SELECT main_category, COUNT(*) as count 
            FROM library 
            GROUP BY main_category
            ''')
            
            for row in cursor.fetchall():
                main_cat = row['main_category'] or "Uncategorized"
                count = row['count']
                
                if main_cat not in categories:
                    categories[main_cat] = {
                        "count": 0,
                        "subcategories": {}
                    }
                
                categories[main_cat]["count"] = count
            
            # Get counts by subcategory
            cursor.execute('''
            SELECT main_category, subcategory, COUNT(*) as count 
            FROM library 
            GROUP BY main_category, subcategory
            ''')
            
            for row in cursor.fetchall():
                main_cat = row['main_category'] or "Uncategorized"
                subcat = row['subcategory'] or "Uncategorized"
                count = row['count']
                
                if main_cat not in categories:
                    categories[main_cat] = {
                        "count": 0,
                        "subcategories": {}
                    }
                
                if "subcategories" not in categories[main_cat]:
                    categories[main_cat]["subcategories"] = {}
                
                categories[main_cat]["subcategories"][subcat] = count
            
            # Get total count
            cursor.execute('SELECT COUNT(*) as total FROM library')
            total = cursor.fetchone()['total']
            
            return {
                "total": total,
                "categories": categories
            }
        
        except sqlite3.Error as e:
            return {"total": 0, "categories": {}}
        
        finally:
            conn.close()
    
    @staticmethod
    def get_library_image(library_id):
        """Get a specific image from the library"""
        conn = sqlite3.connect(SQLITE_DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            # Get the image from library
            cursor.execute('SELECT * FROM library WHERE id = ?', (library_id,))
            img = cursor.fetchone()
            
            if not img:
                return None
            
            # Get tags for this image
            cursor.execute('SELECT tag_name FROM library_tags WHERE library_id = ?', (img['id'],))
            tags = [row['tag_name'] for row in cursor.fetchall()]
            
            # Convert to dictionary
            image_dict = dict(img)
            image_dict['tags'] = tags
            
            return image_dict
        
        except sqlite3.Error:
            return None
        
        finally:
            conn.close()
    
    @staticmethod
    def delete_from_library(library_id):
        """Delete an image from the library"""
        conn = sqlite3.connect(SQLITE_DB_PATH)
        cursor = conn.cursor()
        
        try:
            # Delete image from library (will cascade delete tags)
            cursor.execute('DELETE FROM library WHERE id = ?', (library_id,))
            conn.commit()
            
            return {"success": True, "message": "Image removed from library"}
        
        except sqlite3.Error as e:
            conn.rollback()
            return {"success": False, "message": f"Error removing from library: {str(e)}"}
        
        finally:
            conn.close()
    
    @staticmethod
    def add_custom_tags(library_id, tags_string):
        """Add custom tags to a library image
        
        Args:
            library_id (int): The ID of the library image
            tags_string (str): Comma-separated tags string
            
        Returns:
            dict: Result of the operation
        """
        if not tags_string or not tags_string.strip():
            return {"success": False, "message": "No tags provided"}
        
        # Parse and clean tags
        tags = [tag.strip().lower() for tag in tags_string.split(',') if tag.strip()]
        
        if not tags:
            return {"success": False, "message": "No valid tags provided"}
        
        conn = sqlite3.connect(SQLITE_DB_PATH)
        cursor = conn.cursor()
        
        try:
            # Check if image exists
            cursor.execute('SELECT id FROM library WHERE id = ?', (library_id,))
            if not cursor.fetchone():
                return {"success": False, "message": "Image not found in library"}
                
            # Add each tag
            for tag in tags:
                # Check if tag already exists for this image
                cursor.execute('SELECT id FROM library_tags WHERE library_id = ? AND tag_name = ?', 
                             (library_id, tag))
                if not cursor.fetchone():
                    # Add new tag
                    cursor.execute('INSERT INTO library_tags (library_id, tag_name, is_custom) VALUES (?, ?, 1)',
                                 (library_id, tag))
            
            conn.commit()
            return {
                "success": True, 
                "message": f"Added {len(tags)} custom tags", 
                "tags": tags
            }
            
        except sqlite3.Error as e:
            conn.rollback()
            return {"success": False, "message": f"Error adding custom tags: {str(e)}"}
            
        finally:
            conn.close()
    
    @staticmethod
    def get_library_tags(library_id):
        """Get all tags for a library image, separated into original and custom tags
        
        Args:
            library_id (int): The ID of the library image
            
        Returns:
            dict: Original and custom tags
        """
        conn = sqlite3.connect(SQLITE_DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            # Get original tags
            cursor.execute('SELECT tag_name FROM library_tags WHERE library_id = ? AND is_custom = 0', (library_id,))
            original_tags = [row['tag_name'] for row in cursor.fetchall()]
            
            # Get custom tags
            cursor.execute('SELECT tag_name FROM library_tags WHERE library_id = ? AND is_custom = 1', (library_id,))
            custom_tags = [row['tag_name'] for row in cursor.fetchall()]
            
            return {
                "original_tags": original_tags,
                "custom_tags": custom_tags,
                "all_tags": original_tags + custom_tags
            }
            
        except sqlite3.Error:
            return {"original_tags": [], "custom_tags": [], "all_tags": []}
            
        finally:
            conn.close()
    
    @staticmethod
    def update_image_category(library_id, main_category, subcategory):
        """Update the category for a library image
        
        Args:
            library_id (int): The ID of the library image
            main_category (str): The main category
            subcategory (str): The subcategory
            
        Returns:
            dict: Result of the operation
        """
        # Validate categories
        valid_main_category = main_category in TATTOO_CATEGORIES.keys()
        valid_subcategory = False
        
        if valid_main_category:
            valid_subcategory = subcategory in TATTOO_CATEGORIES[main_category]
        
        if not valid_main_category:
            return {"success": False, "message": f"Invalid main category: {main_category}"}
        
        if not valid_subcategory:
            return {"success": False, "message": f"Invalid subcategory: {subcategory} for {main_category}"}
        
        conn = sqlite3.connect(SQLITE_DB_PATH)
        cursor = conn.cursor()
        
        try:
            # Check if image exists
            cursor.execute('SELECT id FROM library WHERE id = ?', (library_id,))
            if not cursor.fetchone():
                return {"success": False, "message": "Image not found in library"}
            
            # Update category
            cursor.execute('''
            UPDATE library 
            SET main_category = ?, subcategory = ?
            WHERE id = ?
            ''', (main_category, subcategory, library_id))
            
            conn.commit()
            return {
                "success": True,
                "message": f"Updated category to {main_category} / {subcategory}"
            }
        
        except sqlite3.Error as e:
            conn.rollback()
            return {"success": False, "message": f"Error updating category: {str(e)}"}
        
        finally:
            conn.close()
    
    @staticmethod
    def get_available_categories():
        """Get the list of available categories
        
        Returns:
            dict: Available categories
        """
        # Create a copy of the categories to avoid modifying the original
        categories = dict(TATTOO_CATEGORIES)
        
        # Add Uncategorized category
        categories["Uncategorized"] = ["Uncategorized"]
        
        return {
            "main_categories": list(categories.keys()),
            "categories": categories
        }
