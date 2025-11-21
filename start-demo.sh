#!/bin/bash

# Start a simple HTTP server for the demo interface

echo "🚀 Starting demo server..."
echo ""
echo "📱 Open in your browser:"
echo "   http://localhost:8000/demo-interface.html"
echo ""
echo "Press Ctrl+C to stop"
echo ""

python3 -m http.server 8000

