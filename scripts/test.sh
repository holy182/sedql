#!/bin/bash
# SEDQL Test Script
# This script runs all tests for SEDQL

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}================================${NC}"
echo -e "${BLUE}  SEDQL Test Script v2.0        ${NC}"
echo -e "${BLUE}================================${NC}"
echo ""

# Get project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo -e "${YELLOW}Project Root:${NC} $PROJECT_ROOT"
echo ""

# Find Python command
if command_exists python3; then
    PYTHON_CMD="python3"
elif command_exists python; then
    PYTHON_CMD="python"
else
    echo -e "${RED}Error: Python not found${NC}"
    exit 1
fi

echo -e "${YELLOW}Using Python:${NC} $($PYTHON_CMD --version)"
echo ""

# Install test dependencies
echo -e "${YELLOW}Installing test dependencies...${NC}"
$PYTHON_CMD -m pip install pytest pytest-cov pytest-xdist pytest-timeout
echo -e "  ${GREEN}Test dependencies installed${NC}"
echo ""

# Run tests with coverage
echo -e "${YELLOW}Running tests with coverage...${NC}"
echo ""

# Function to run tests
run_tests() {
    local test_type="$1"
    local test_args="$2"
    
    echo -e "${BLUE}--- $test_type ---${NC}"
    
    if [ -z "$test_args" ]; then
        $PYTHON_CMD -m pytest tests/ -v --tb=short \
            --cov=src/sedql \
            --cov-report=html \
            --cov-report=term \
            --cov-report=xml:coverage.xml \
            --timeout=30
    else
        $PYTHON_CMD -m pytest $test_args -v --tb=short \
            --cov=src/sedql \
            --cov-report=html \
            --cov-report=term \
            --cov-report=xml:coverage.xml \
            --timeout=30
    fi
}

# Run different test suites
echo -e "${BLUE}Test Suites:${NC}"
echo "  1. All tests (full suite)"
echo "  2. Unit tests only"
echo "  3. Integration tests only"
echo "  4. Quick tests (smoke test)"
echo "  5. Custom test path"
echo ""

read -p "Select test suite (1-5): " -n 1 -r
echo ""

case $REPLY in
    1)
        echo -e "${YELLOW}Running full test suite...${NC}"
        run_tests "Full Suite"
        ;;
    2)
        echo -e "${YELLOW}Running unit tests...${NC}"
        run_tests "Unit Tests" "tests/ -m 'not integration'"
        ;;
    3)
        echo -e "${YELLOW}Running integration tests...${NC}"
        run_tests "Integration Tests" "tests/ -m integration"
        ;;
    4)
        echo -e "${YELLOW}Running quick tests...${NC}"
        run_tests "Quick Tests" "tests/ -m 'not slow'"
        ;;
    5)
        echo -e "${YELLOW}Enter test path:${NC}"
        read -r test_path
        run_tests "Custom Tests" "$test_path"
        ;;
    *)
        echo -e "${RED}Invalid selection${NC}"
        exit 1
        ;;
esac

echo ""

# Show coverage report
echo -e "${BLUE}================================${NC}"
echo -e "${GREEN}Coverage Report${NC}"
echo -e "${BLUE}================================${NC}"
echo ""

# Check if coverage report exists
if [ -f "coverage.xml" ]; then
    # Parse coverage summary
    TOTAL_COV=$(grep -o 'line-rate="[0-9.]*"' coverage.xml | head -1 | sed 's/line-rate="//' | sed 's/"//')
    if [ -n "$TOTAL_COV" ]; then
        PERCENT=$(echo "scale=2; $TOTAL_COV * 100" | bc)
        echo -e "  Total Coverage: ${GREEN}$PERCENT%${NC}"
    fi
    
    # Show coverage by module
    echo ""
    echo -e "${YELLOW}Coverage by module:${NC}"
    echo "  (See htmlcov/index.html for detailed report)"
    echo ""
    
    # Check if coverage is above threshold
    THRESHOLD=70
    if (( $(echo "$TOTAL_COV >= $THRESHOLD" | bc -l) )); then
        echo -e "  ${GREEN}Coverage meets threshold ($THRESHOLD%)${NC}"
    else
        echo -e "  ${RED}Coverage below threshold ($THRESHOLD%)${NC}"
    fi
else
    echo -e "  ${YELLOW}No coverage report generated${NC}"
fi

echo ""

# Run linting if available
echo -e "${YELLOW}Checking code quality...${NC}"

if $PYTHON_CMD -c "import flake8" 2>/dev/null; then
    echo "  Running flake8..."
    $PYTHON_CMD -m flake8 src/ --count --statistics || true
else
    echo "  ${YELLOW}flake8 not available${NC}"
fi

if $PYTHON_CMD -c "import black" 2>/dev/null; then
    echo "  Running black check..."
    $PYTHON_CMD -m black --check src/ 2>/dev/null || true
else
    echo "  ${YELLOW}black not available${NC}"
fi

echo ""

# Test CLI commands
echo -e "${BLUE}================================${NC}"
echo -e "${GREEN}Testing CLI Commands${NC}"
echo -e "${BLUE}================================${NC}"
echo ""

# Check if sedql is installed
if $PYTHON_CMD -c "import sedql" 2>/dev/null; then
    echo -e "${YELLOW}Testing CLI...${NC}"
    
    # Test --help
    echo "  Testing: sedql --help"
    $PYTHON_CMD -m sedql.cli.main --help 2>/dev/null || true
    echo ""
    
    # Test status if config exists
    if [ -f "sedql.config.json" ]; then
        echo "  Testing: sedql status"
        $PYTHON_CMD -m sedql.cli.main status 2>/dev/null || true
        echo ""
    fi
    
    # Test list-entities if semantic layer exists
    if [ -f "semantic_layer.json" ]; then
        echo "  Testing: sedql list-entities"
        $PYTHON_CMD -m sedql.cli.main list-entities 2>/dev/null || true
        echo ""
    fi
else
    echo -e "  ${YELLOW}SEDQL not installed, skipping CLI tests${NC}"
fi

echo ""

# Summary
echo -e "${BLUE}================================${NC}"
echo -e "${GREEN}Test Summary${NC}"
echo -e "${BLUE}================================${NC}"
echo ""

# Check if any tests failed
if [ -f ".pytest_cache" ]; then
    echo -e "  ${GREEN}Tests completed${NC}"
else
    echo -e "  ${YELLOW}No test cache found${NC}"
fi

echo ""
echo -e "  Coverage report: ${YELLOW}htmlcov/index.html${NC}"
echo -e "  Coverage XML: ${YELLOW}coverage.xml${NC}"
echo ""

echo -e "${GREEN}Done!${NC}"