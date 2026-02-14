#!/bin/bash
# Migration deployment script for GTIXT validation framework
# Usage: ./deploy-validation.sh [environment]

set -e

ENVIRONMENT=${1:-local}
MIGRATIONS_DIR="src/gpti_bot/db/migrations"

echo "🚀 GTIXT Validation Framework Deployment"
echo "   Environment: $ENVIRONMENT"
echo ""

# Check if running in Docker or locally
if command -v docker-compose &> /dev/null; then
    DB_CMD="docker-compose exec -T postgres psql -U gpti -d gpti_data"
    DOCKER=true
else
    DB_CMD="psql -U gpti -d gpti_data"
    DOCKER=false
fi

echo "📋 Found migrations:"
for file in $(ls -1 $MIGRATIONS_DIR/*.sql | sort); do
    echo "  ✓ $(basename $file)"
done
echo ""

# Check database connection
echo "🔗 Testing database connection..."
if $DOCKER; then
    echo "   Using Docker Compose"
    docker-compose ps postgres > /dev/null || {
        echo "   ❌ Database container not running!"
        exit 1
    }
else
    echo "   Using local PostgreSQL"
    psql -h localhost -U gpti -d gpti_data -c "SELECT 1" > /dev/null || {
        echo "   ❌ Cannot connect to database!"
        exit 1
    }
fi
echo "   ✓ Connection OK"
echo ""

# Run migrations in order
echo "📦 Running migrations..."
for file in $(ls -1 $MIGRATIONS_DIR/*.sql | sort); do
    migration_name=$(basename $file)
    echo "   → Applying $migration_name..."
    
    if $DOCKER; then
        cat $file | docker-compose exec -T postgres psql -U gpti -d gpti_data > /dev/null
    else
        psql -U gpti -d gpti_data -f $file > /dev/null
    fi
    
    if [ $? -eq 0 ]; then
        echo "     ✓ Applied"
    else
        echo "     ❌ Failed!"
        exit 1
    fi
done
echo ""

# Verify tables created
echo "✅ Verifying tables..."
verification_query="
    SELECT table_name FROM information_schema.tables 
    WHERE table_schema = 'public' AND table_name IN ('events', 'validation_metrics', 'validation_alerts')
    ORDER BY table_name;
"

if $DOCKER; then
    result=$(echo "$verification_query" | docker-compose exec -T postgres psql -U gpti -d gpti_data -t | grep -E 'events|validation' | wc -l)
else
    result=$(echo "$verification_query" | psql -U gpti -d gpti_data -t | grep -E 'events|validation' | wc -l)
fi

if [ "$result" -ge 3 ]; then
    echo "   ✓ events table"
    echo "   ✓ validation_metrics table"
    echo "   ✓ validation_alerts table"
else
    echo "   ❌ Table verification failed!"
    exit 1
fi
echo ""

# Show summary
echo "📊 Event data summary:"
if $DOCKER; then
    docker-compose exec -T postgres psql -U gpti -d gpti_data -c "SELECT COUNT(*) as total_events FROM events;"
else
    psql -U gpti -d gpti_data -c "SELECT COUNT(*) as total_events FROM events;"
fi
echo ""

echo "🎉 Validation framework deployed successfully!"
echo ""
echo "Next steps:"
echo "  1. Verify database connection: psql -U gpti -d gpti_data -c 'SELECT COUNT(*) FROM events;'"
echo "  2. Schedule validation_flow: prefect deployment create -f flows/validation_flow.py"
echo "  3. Configure Slack webhook: export SLACK_VALIDATION_WEBHOOK='https://hooks.slack.com/...'"
echo "  4. Test validation: python -m flows.validation_flow"
echo ""
