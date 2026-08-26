#!/bin/bash
# SEDQL Build Script
# This script builds and packages SEDQL for distribution

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}================================${NC}"
echo -e "${BLUE}  SEDQL Build Script v2.0       ${NC}"
echo -e "${BLUE}================================${NC}"
echo ""

# Get project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo -e "${YELLOW}Project Root:${NC} $PROJECT_ROOT"
echo ""

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check Python version
echo -e "${YELLOW}Checking Python version...${NC}"
if command_exists python3; then
    PYTHON_CMD="python3"
elif command_exists python; then
    PYTHON_CMD="python"
else
    echo -e "${RED}Error: Python not found${NC}"
    exit 1
fi

PYTHON_VERSION=$($PYTHON_CMD -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo -e "  Python version: ${GREEN}$PYTHON_VERSION${NC}"

# Check Python version >= 3.9
if [[ $(echo "$PYTHON_VERSION < 3.9" | bc) -eq 1 ]]; then
    echo -e "${RED}Error: Python 3.9 or higher required${NC}"
    exit 1
fi

echo ""

# Clean previous builds
echo -e "${YELLOW}Cleaning previous builds...${NC}"
rm -rf build/
rm -rf dist/
rm -rf *.egg-info
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
echo -e "  ${GREEN}Clean complete${NC}"
echo ""

# Install build dependencies
echo -e "${YELLOW}Installing build dependencies...${NC}"
$PYTHON_CMD -m pip install --upgrade pip setuptools wheel build twine
echo -e "  ${GREEN}Dependencies installed${NC}"
echo ""

# Install project dependencies
echo -e "${YELLOW}Installing project dependencies...${NC}"
if [ -f "requirements.txt" ]; then
    $PYTHON_CMD -m pip install -r requirements.txt
    echo -e "  ${GREEN}Requirements installed${NC}"
else
    echo -e "  ${YELLOW}No requirements.txt found${NC}"
fi
echo ""

# Install in development mode
echo -e "${YELLOW}Installing SEDQL in development mode...${NC}"
$PYTHON_CMD -m pip install -e .
echo -e "  ${GREEN}Development installation complete${NC}"
echo ""

# Run tests if pytest is available
echo -e "${YELLOW}Running tests...${NC}"
if $PYTHON_CMD -c "import pytest" 2>/dev/null; then
    $PYTHON_CMD -m pytest tests/ -v --tb=short || true
else
    echo -e "  ${YELLOW}No pytest found, skipping tests${NC}"
fi
echo ""

# Build package
echo -e "${YELLOW}Building package...${NC}"
$PYTHON_CMD -m build
echo -e "  ${GREEN}Build complete${NC}"
echo ""

# Check package
echo -e "${YELLOW}Checking package...${NC}"
$PYTHON_CMD -m twine check dist/*
echo -e "  ${GREEN}Package check complete${NC}"
echo ""

# Generate semantic layer examples
echo -e "${YELLOW}Generating examples...${NC}"
if [ -f "test.db" ]; then
    echo -e "  ${YELLOW}Found test.db, generating semantic layer...${NC}"
    $PYTHON_CMD -m sedql.cli.main init --db "sqlite:///test.db" --output "examples/semantic_layer_example.json" 2>/dev/null || true
fi
echo ""

# Show results
echo -e "${BLUE}================================${NC}"
echo -e "${GREEN}Build Complete!${NC}"
echo -e "${BLUE}================================${NC}"
echo ""
echo -e "  Package: ${GREEN}dist/sedql-*.whl${NC}"
echo -e "  Source: ${GREEN}dist/sedql-*.tar.gz${NC}"
echo ""
echo -e "To install:"
echo -e "  ${YELLOW}pip install dist/sedql-*.whl${NC}"
echo ""
echo -e "To test:"
echo -e "  ${YELLOW}sedql --help${NC}"
echo ""

# Ask if user wants to run tests
read -p "Run tests? (y/n): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Running tests...${NC}"
    $PYTHON_CMD -m pytest tests/ -v --tb=short
fi

echo -e "${GREEN}Done!${NC}"