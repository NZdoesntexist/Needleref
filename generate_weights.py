
from app import app, db
from models import Image, Tag
import logging

def generate_weights_from_tags(image):
    weights = {}
    for tag in image.tags:
        category = (tag.category or "general").lower()
        name = tag.name.lower()
        key = f"{category}.{name}"
        weights[key] = 1.0
    return weights

def run():
    with app.app_context():
        try:
            updated = 0
            images = Image.query.all()
            
            for image in images:
                if image.weights:  # Skip if already has weights
                    continue
                    
                weights = generate_weights_from_tags(image)
                image.weights = weights  # Store as native JSON
                db.session.add(image)
                updated += 1
                
                if updated % 100 == 0:  # Log progress every 100 images
                    logging.info(f"Processed {updated} images...")
            
            db.session.commit()
            print(f"✅ Added weights to {updated} images.")
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error generating weights: {str(e)}")
            print("❌ Failed to generate weights. Check logs for details.")

if __name__ == "__main__":
    run()
