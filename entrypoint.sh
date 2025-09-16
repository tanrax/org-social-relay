#!/bin/bash
set -e

echo "🚀 Starting Django application..."

# Install dependencies
echo "📦 Installing dependencies..."
uv sync --no-dev

# Run migrations
echo "🔄 Running database migrations..."
uv run python manage.py migrate

# Check for any issues
echo "🔍 Checking Django configuration..."
uv run python manage.py check

# Start Django development server
echo "🎯 Starting Django development server on 0.0.0.0:8000..."
exec uv run python manage.py runserver 0.0.0.0:8000