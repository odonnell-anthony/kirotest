#!/bin/bash
# Development setup script for Wiki Documentation App

set -e

echo "=== Wiki Documentation App - Development Setup ==="

# Create necessary directories
echo "Creating directories..."
mkdir -p logs uploads static/css static/js

# Set permissions for log directory
chmod 755 logs uploads

# Create basic log files
touch logs/app.log logs/error.log

echo "Development setup completed successfully!"
echo ""
echo "To start the application:"
echo "  docker-compose up -d"
echo ""
echo "To view logs:"
echo "  docker-compose logs -f"
echo ""
echo "To access the application:"
echo "  http://localhost:8000"
echo ""
echo "To access the API documentation:"
echo "  http://localhost:8000/api/docs"