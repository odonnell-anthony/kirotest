# Technology Stack & Build System

## Core Technologies

### Backend Framework
- **FastAPI**: Modern, fast web framework for building APIs with Python 3.11+
- **Uvicorn**: ASGI server for development
- **Gunicorn**: Production WSGI server

### Database & Storage
- **PostgreSQL 15**: Primary database with full-text search capabilities
- **SQLAlchemy 2.0**: ORM with async support
- **Alembic**: Database migration management
- **Redis 7**: Caching and session management

### Authentication & Security
- **JWT**: Token-based authentication with python-jose
- **Passlib**: Password hashing with bcrypt
- **Rate Limiting**: slowapi for API rate limiting
- **CORS**: Cross-origin resource sharing support

### Background Processing
- **Celery**: Distributed task queue for background jobs
- **Redis**: Message broker for Celery

### Development & Quality
- **Pytest**: Testing framework with async support
- **Black**: Code formatting
- **isort**: Import sorting
- **Flake8**: Linting
- **MyPy**: Static type checking

### Containerization
- **Docker**: Application containerization
- **Docker Compose**: Multi-container orchestration

## Common Commands

### Development Setup
```bash
# Start development environment
docker-compose up -d

# Local development (with virtual environment)
python -m venv venv
source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Database Operations
```bash
# Create new migration
python scripts/create_migration.py "migration_description"

# Run migrations
python scripts/migrate.py

# Database optimization
python scripts/optimize_database.py
```

### Testing
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html
```

### Code Quality
```bash
# Format code
black app/
isort app/

# Lint code
flake8 app/
mypy app/
```

### Production Deployment
```bash
# Production deployment
docker-compose -f docker-compose.prod.yml --env-file .env.prod up -d
```

## Configuration Management

- Environment variables via `.env` files
- Pydantic Settings for type-safe configuration
- Separate configs for development/production
- Docker environment variable injection

## Key Dependencies

- **FastAPI 0.104.1**: Web framework
- **SQLAlchemy 2.0.23**: Database ORM
- **Redis 5.0.1**: Caching layer
- **Celery 5.3.4**: Background tasks
- **Pydantic 2.5.0**: Data validation
- **Structlog 23.2.0**: Structured logging