# NeedleRef

A robust web application empowering tattoo artists with intelligent image discovery and management tools, leveraging advanced image processing and search technologies.

## Features

- Multi-source image search from Unsplash, Pexels, and Pixabay APIs
- Concurrent search capabilities for faster results
- Smart keyword expansion for better search results
- Image result reranking based on relevance
- Infinite scroll for easy browsing
- Graceful handling of unavailable APIs

## Technologies Used

- **Backend**: Python Flask with async support
- **Database**: PostgreSQL and SQLite
- **Search**: Concurrent multi-source image search with intelligent scoring
- **Image Processing**: RapidFuzz for smart matching
- **Frontend**: Responsive JavaScript interface

## Setup

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Set up API keys for image services in your environment variables:
   - `UNSPLASH_API_KEY` - for Unsplash image search
   - `PEXELS_API_KEY` - for Pexels image search
   - `PIXABAY_API_KEY` - for Pixabay image search
   - `DATABASE_URL` - PostgreSQL database connection string
4. Run the application: `gunicorn --bind 0.0.0.0:5000 main:app`

## License

[MIT](LICENSE)