#!/bin/bash
set -e

echo "🚀 Starting Django application..."

# Run migrations
echo "🔄 Running database migrations..."
python manage.py migrate

# Check for any issues
echo "🔍 Checking Django configuration..."
python manage.py check

# Start application server
echo "🎯 Starting uvicorn on 0.0.0.0:8000..."
exec uvicorn core.asgi:application --host 0.0.0.0 --port 8000 --workers 4