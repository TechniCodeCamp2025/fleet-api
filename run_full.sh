#!/bin/bash
# Full optimization script

echo "🚀 Fleet Optimization - Full Run"
echo "================================="
echo ""
echo "⚠️  This will process ALL routes and may take 15-60 minutes."
echo ""
read -p "Continue? (y/n) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

echo ""
echo "Starting full optimization..."
echo ""

cd "$(dirname "$0")"
python src/main.py full

exit_code=$?

if [ $exit_code -eq 0 ]; then
    echo ""
    echo "✅ Optimization completed successfully!"
    echo "📁 Check the output/ directory for results"
else
    echo ""
    echo "❌ Optimization failed with exit code $exit_code"
fi

exit $exit_code

