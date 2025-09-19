# Org Social Relay - Task Management Makefile
# Usage: make <command>

.PHONY: help start stop restart clean-feeds run-tasks run-task-1 run-task-2 run-task-3 test logs status shell

# Default help command
help:
	@echo "Org Social Relay - Available Commands:"
	@echo ""
	@echo "🐳 Docker Management:"
	@echo "  start         - Start all containers"
	@echo "  stop          - Stop all containers"
	@echo "  restart       - Restart all containers"
	@echo "  logs          - Show container logs"
	@echo "  status        - Show container status"
	@echo ""
	@echo "🗂️  Database Management:"
	@echo "  clean-feeds   - Clean all feeds from database"
	@echo "  shell         - Open Django shell"
	@echo ""
	@echo "⚙️  Task Execution (in order):"
	@echo "  run-tasks     - Run all tasks sequentially and ordered"
	@echo "  run-task-1    - Run task 1: Discover feeds from relay nodes & registers"
	@echo "  run-task-2    - Run task 2: Discover feeds from follows"
	@echo "  run-task-3    - Run task 3: Scan all feeds for posts and profiles"
	@echo ""
	@echo "🧪 Testing:"
	@echo "  test          - Run all tests"
	@echo "  test-feeds    - Run feeds tests only"
	@echo "  test-parser   - Run parser tests only"
	@echo "  test-mentions - Run mentions tests only"
	@echo ""
	@echo "📊 Monitoring:"
	@echo "  feed-count    - Show current feed count"
	@echo "  feed-list     - List all feeds via API"
	@echo ""

# Docker Management
start:
	@echo "🐳 Starting containers..."
	docker compose up -d

stop:
	@echo "🐳 Stopping containers..."
	docker compose down

restart:
	@echo "🐳 Restarting containers..."
	docker compose down
	docker compose up -d

logs:
	@echo "📋 Showing container logs..."
	docker compose logs --tail=50 -f

status:
	@echo "📊 Container status:"
	docker compose ps

# Database Management
clean-feeds:
	@echo "🗂️  Cleaning feeds table..."
	docker exec org-social-relay-django-1 python manage.py shell -c "from app.feeds.models import Feed; print(f'Deleted {Feed.objects.count()} feeds'); Feed.objects.all().delete()"

shell:
	@echo "🐚 Opening Django shell..."
	docker exec -it org-social-relay-django-1 python manage.py shell

# Task Execution
run-tasks: run-task-1 run-task-2 run-task-3
	@echo "✅ All tasks completed!"

run-task-1:
	@echo "⚙️  Running Task 1: Discover feeds from relay nodes & public register..."
	@echo "📊 Feeds before: $$(docker exec org-social-relay-django-1 python manage.py shell -c 'from app.feeds.models import Feed; print(Feed.objects.count())' 2>/dev/null)"
	docker exec org-social-relay-django-1 python manage.py shell -c "from app.feeds.tasks import discover_feeds_from_relay_nodes; discover_feeds_from_relay_nodes()"
	@echo "📊 Feeds after: $$(docker exec org-social-relay-django-1 python manage.py shell -c 'from app.feeds.models import Feed; print(Feed.objects.count())' 2>/dev/null)"
	@echo ""

run-task-2:
	@echo "⚙️  Running Task 2: Discover feeds from follows..."
	@echo "📊 Feeds before: $$(docker exec org-social-relay-django-1 python manage.py shell -c 'from app.feeds.models import Feed; print(Feed.objects.count())' 2>/dev/null)"
	docker exec org-social-relay-django-1 python manage.py shell -c "from app.feeds.tasks import discover_new_feeds_from_follows; discover_new_feeds_from_follows()"
	@echo "📊 Feeds after: $$(docker exec org-social-relay-django-1 python manage.py shell -c 'from app.feeds.models import Feed; print(Feed.objects.count())' 2>/dev/null)"
	@echo ""

run-task-3:
	@echo "⚙️  Running Task 3: Scan feeds for posts and profiles..."
	@echo "📊 Profiles/Posts before: $$(docker exec org-social-relay-django-1 python manage.py shell -c 'from app.feeds.models import Profile, Post; print(f\"Profiles: {Profile.objects.count()}, Posts: {Post.objects.count()}\")' 2>/dev/null)"
	docker exec org-social-relay-django-1 python manage.py shell -c "from app.feeds.tasks import scan_feeds; scan_feeds()"
	@echo "📊 Profiles/Posts after: $$(docker exec org-social-relay-django-1 python manage.py shell -c 'from app.feeds.models import Profile, Post; print(f\"Profiles: {Profile.objects.count()}, Posts: {Post.objects.count()}\")' 2>/dev/null)"
	@echo ""

# Testing
test:
	@echo "🧪 Running all tests..."
	docker exec org-social-relay-django-1 python manage.py test

test-feeds:
	@echo "🧪 Running feeds tests..."
	docker exec org-social-relay-django-1 python manage.py test app.feeds.test_feeds

test-parser:
	@echo "🧪 Running parser tests..."
	docker exec org-social-relay-django-1 python manage.py test app.feeds.test_parser

test-mentions:
	@echo "🧪 Running mentions tests..."
	docker exec org-social-relay-django-1 python manage.py test app.feeds.test_mentions

# Monitoring
feed-count:
	@echo "📊 Current feed count:"
	@docker exec org-social-relay-django-1 python manage.py shell -c "from app.feeds.models import Feed, Profile, Post; print(f'Feeds: {Feed.objects.count()}'); print(f'Profiles: {Profile.objects.count()}'); print(f'Posts: {Post.objects.count()}')" 2>/dev/null

feed-list:
	@echo "📋 Current feeds (via API):"
	@curl -s http://localhost:8080/feeds/ | python3 -m json.tool 2>/dev/null || echo "API not available"

# API testing
test-mentions-api:
	@echo "🔍 Testing mentions API..."
	@echo "Testing mentions API without feed parameter:"
	@curl -s http://localhost:8080/mentions/ | python3 -m json.tool 2>/dev/null
	@echo ""
	@echo "Testing mentions API with non-existent feed:"
	@curl -s "http://localhost:8080/mentions/?feed=https://nonexistent.example.com/social.org" | python3 -m json.tool 2>/dev/null

# Validation test
test-validation:
	@echo "🔍 Testing feed validation..."
	@echo "Testing valid feed:"
	@curl -s -X POST http://localhost:8080/feeds/ -H "Content-Type: application/json" -d '{"feed": "https://andros.dev/static/social.org"}' | python3 -m json.tool 2>/dev/null
	@echo ""
	@echo "Testing invalid feed:"
	@curl -s -X POST http://localhost:8080/feeds/ -H "Content-Type: application/json" -d '{"feed": "https://example.com/invalid.org"}' | python3 -m json.tool 2>/dev/null