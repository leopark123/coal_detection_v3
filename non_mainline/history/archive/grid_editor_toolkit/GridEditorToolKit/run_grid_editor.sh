#!/bin/bash
echo "=========================================="
echo "     Grid Editor Toolkit v1.0.0"
echo "=========================================="
echo

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    if ! command -v python &> /dev/null; then
        echo "[ERROR] Python not found! Please install Python 3.7+ first."
        echo "Visit: https://www.python.org/downloads/"
        exit 1
    else
        PYTHON_CMD=python
    fi
else
    PYTHON_CMD=python3
fi

echo "Using Python: $(which $PYTHON_CMD)"

# Check if required packages are installed
echo "Checking dependencies..."
$PYTHON_CMD -c "import cv2, numpy" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "[WARN] Required packages not found. Installing dependencies..."
    pip3 install -r requirements.txt || pip install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo "[ERROR] Failed to install dependencies."
        echo "You may need to install system packages:"
        echo "  Ubuntu/Debian: sudo apt-get install python3-opencv python3-numpy"
        echo "  CentOS/RHEL: sudo yum install python3-opencv python3-numpy"
        echo "  macOS: brew install opencv python-numpy"
        exit 1
    fi
fi

echo "[OK] Dependencies verified."
echo

# Show available sample images
echo "Available sample images:"
[ -f "samples/sample_image.png" ] && echo "  [1] samples/sample_image.png"
[ -f "samples/sample_image2.png" ] && echo "  [2] samples/sample_image2.png"
[ -f "samples/sample_image3.png" ] && echo "  [3] samples/sample_image3.png"
echo "  [C] Custom image path"
echo

read -p "Select image [1-3] or C for custom: " choice

case $choice in
    1)
        IMAGE_PATH="samples/sample_image.png"
        ;;
    2)
        IMAGE_PATH="samples/sample_image2.png"
        ;;
    3)
        IMAGE_PATH="samples/sample_image3.png"
        ;;
    [Cc])
        read -p "Enter image path: " IMAGE_PATH
        ;;
    *)
        IMAGE_PATH="samples/sample_image.png"
        ;;
esac

# Get grid dimensions
read -p "Grid rows (default 14): " rows
read -p "Grid columns (default 10): " cols

rows=${rows:-14}
cols=${cols:-10}

echo
echo "Starting Grid Editor..."
echo "Image: $IMAGE_PATH"
echo "Grid: $rows rows x $cols columns"
echo

# Make sure the script has execute permission
chmod +x "$0" 2>/dev/null || true

# Run the grid editor
$PYTHON_CMD src/grid_editor.py --image "$IMAGE_PATH" --rows $rows --cols $cols

echo
echo "Grid Editor finished."
read -p "Press Enter to continue..."