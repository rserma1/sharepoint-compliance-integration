#!/bin/bash

echo "=========================================="
echo "SharePoint Integration Setup"
echo "=========================================="
echo ""

# Check Python version
echo "Checking Python version..."
python3 --version

# Create virtual environment (optional but recommended)
read -p "Create virtual environment? (y/n): " create_venv
if [ "$create_venv" = "y" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    echo "✅ Virtual environment created and activated"
fi

# Install dependencies
echo ""
echo "Installing dependencies..."
pip install -r requirements.txt

# Setup environment file
echo ""
if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "✅ .env file created"
    echo ""
    echo "⚠️  IMPORTANT: Edit .env file and add your credentials:"
    echo "   - SHAREPOINT_CLIENT_SECRET"
    echo "   - SHAREPOINT_TENANT_ID"
    echo ""
else
    echo "✅ .env file already exists"
fi

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Edit .env file with your credentials"
echo "2. Run: python process_sharepoint_data.py"
echo ""
