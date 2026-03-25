#!/bin/bash
# Run Gold Trading Strategy
# Usage: ./run.sh

cd "$(dirname "$0")"

echo "Running Gold Trading Strategy..."
python3 gold_trader.py

echo ""
echo "✅ Strategy execution complete"
