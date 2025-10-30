#!/bin/bash
# Quick test script for fleet optimization

echo "🚀 Fleet Optimization - Quick Test"
echo "=================================="
echo ""

# Check if Python is available
if ! command -v python &> /dev/null; then
    echo "❌ Python not found. Please install Python 3.13+"
    exit 1
fi

# Check Python version
python_version=$(python -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo "✓ Python version: $python_version"

# Check if data directory exists
if [ ! -d "data" ]; then
    echo "❌ Data directory not found!"
    exit 1
fi

echo "✓ Data directory found"

# Check if config exists
if [ ! -f "algorithm_config.json" ]; then
    echo "❌ algorithm_config.json not found!"
    exit 1
fi

echo "✓ Configuration file found"
echo ""

# Run quick test
echo "Running quick test with 1000 routes..."
echo ""

cd "$(dirname "$0")"
python src/main.py test 1000

exit_code=$?

if [ $exit_code -eq 0 ]; then
    echo ""
    echo "✅ Test completed successfully!"
    echo "📁 Check the output/ directory for results"
else
    echo ""
    echo "❌ Test failed with exit code $exit_code"
fi

exit $exit_code

