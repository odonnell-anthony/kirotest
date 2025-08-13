# Project Structure & Architecture

## Directory Organization

```
app/
├── __init__.py
├── main.py                 # FastAPI application entry point
├── api/                    # API route handlers (controllers)
│   ├── auth.py            # Authentication endpoints
│   ├── documents.py       # Document CRUD endpoints
│   ├── folders.py         # Folder management endpoints
│   ├── files.py           # File upload/download endpoints
│   ├── comments.py        # Comment system endpoints
│   ├── tags.py            # Tag management endpoints
│   ├── search.py          # Search functionality endpoints
│   ├── timeline.py        # Activity timeline endpoints
│   ├── admin.py           # Administrative endpoints
│   ├── webhooks.py        # Webhook endpoints
│   ├── permissions.py     # Permission management endpoints
│   └── health.py          # Health check endpoints
├── core/                   # Core application infrastructure
│   ├── config.py          # Application configuration
│   ├── database.py        # Database connection and session management
│   ├── redis.py           # Redis connection management
│   ├── auth.py            # Authentication utilities
│   ├── security.py        # Security middleware and utilities
│   ├── logging.py         # Structured logging setup
│   ├── rate_limit.py      # Rate limiting middleware
│   ├── celery.py          # Celery configuration
│   └── exceptions.py      # Custom exception classes
├── models/                 # SQLAlchemy database models
│   ├── user.py            # User model
│   ├── document.py        # Document model
│   ├── revision.py        # Document revision model
│   ├── folder.py          # Folder model
│   ├── file.py            # File attachment model
│   ├── comment.py         # Comment model
│   ├── tag.py             # Tag and DocumentTag models
│   ├── permission.py      # Permission model
│   └── audit.py           # Audit log model
├── schemas/                # Pydantic schemas for API serialization
│   ├── document.py        # Document request/response schemas
│   ├── folder.py          # Folder schemas
│   ├── comment.py         # Comment schemas
│   ├── tag.py             # Tag schemas
│   ├── search.py          # Search schemas
│   ├── timeline.py        # Timeline schemas
│   ├── admin.py           # Admin schemas
│   └── responses.py       # Common response schemas
├── services/               # Business logic layer
│   ├── auth.py            # Authentication service
│   ├── document.py        # Document management service
│   ├── folder.py          # Folder management service
│   ├── file.py            # File handling service
│   ├── comment.py         # Comment service
│   ├── tag.py             # Tag management service
│   ├── search.py          # Search service
│   ├── timeline.py        # Timeline service
│   ├── permission.py      # Permission service
│   ├── audit.py           # Audit logging service
│   └── webhook.py         # Webhook service
├── tasks/                  # Celery background tasks
└── templates/              # Jinja2 templates (if needed)
```

## Architecture Patterns

### Layered Architecture
1. **API Layer** (`app/api/`): FastAPI routers handling HTTP requests/responses
2. **Service Layer** (`app/services/`): Business logic and operations
3. **Data Layer** (`app/models/`): SQLAlchemy models and database operations
4. **Schema Layer** (`app/schemas/`): Pydantic models for serialization/validation

### Key Conventions

#### File Naming
- Use snake_case for all Python files and directories
- Model files are singular (e.g., `user.py`, `document.py`)
- Service files match their corresponding models
- API files are plural for resource collections

#### Import Organization
- Standard library imports first
- Third-party imports second
- Local application imports last
- Use absolute imports from `app.` root

#### Database Models
- All models inherit from `Base` in `app.core.database`
- Use UUID primary keys for all entities
- Include `created_at` and `updated_at` timestamps
- Use SQLAlchemy 2.0 syntax with `Mapped` annotations
- Define relationships with proper cascade options

#### Services
- Each service class takes `AsyncSession` in constructor
- Use dependency injection pattern
- Handle all business logic and validation
- Raise custom exceptions from `app.core.exceptions`
- Include comprehensive logging

#### API Endpoints
- Use FastAPI dependency injection for database sessions and auth
- Convert service exceptions to appropriate HTTP status codes
- Use Pydantic schemas for request/response validation
- Include comprehensive docstrings for OpenAPI documentation

#### Error Handling
- Custom exceptions in `app.core.exceptions`
- Service layer raises business logic exceptions
- API layer converts to HTTP status codes
- Structured logging for all errors with correlation IDs

## Configuration Management

- Environment-based configuration via Pydantic Settings
- `.env` files for local development
- Docker environment variables for containerized deployment
- Separate production configuration files

## Database Migrations

- Alembic migrations in `alembic/versions/`
- Use descriptive migration names with sequence numbers
- Include both upgrade and downgrade operations
- Test migrations in development before production deployment