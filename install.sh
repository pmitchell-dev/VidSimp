#!/bin/bash
set -e

echo "======================================"
echo "    Installing VidSimp for SteamOS    "
echo "======================================"

# Define installation directory
INSTALL_DIR="$HOME/VidSimp"

# Check for git
if ! command -v git &> /dev/null; then
    echo "Error: git is not installed."
    exit 1
fi

# Clone or pull the repository
if [ -d "$INSTALL_DIR" ]; then
    echo "Directory $INSTALL_DIR already exists. Updating..."
    cd "$INSTALL_DIR"
    git pull
else
    echo "Cloning repository to $INSTALL_DIR..."
    git clone https://github.com/pmitchell-dev/VidSimp.git "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# Set up Python virtual environment to avoid modifying SteamOS system python
echo "Setting up isolated Python environment..."
python3 -m venv venv
source venv/bin/activate

# Install dependencies
echo "Installing required Python packages (PyQt6, python-vlc)..."
pip install --upgrade pip
pip install -r requirements.txt

# Create an easy launcher script
echo "Creating launcher script..."
cat << 'EOF' > launch.sh
#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
python3 vidsimp.py
EOF
chmod +x launch.sh

# Create a .desktop shortcut so it shows up in SteamOS Desktop Mode
echo "Creating application shortcut..."
mkdir -p "$HOME/.local/share/applications"
DESKTOP_FILE="$HOME/.local/share/applications/vidsimp.desktop"

cat << EOF > "$DESKTOP_FILE"
[Desktop Entry]
Version=1.0
Type=Application
Name=VidSimp
Comment=A simple, touch-friendly video player
Exec=$INSTALL_DIR/launch.sh
Icon=$INSTALL_DIR/fullscreen.svg
Terminal=false
Categories=AudioVideo;Player;
EOF
chmod +x "$DESKTOP_FILE"

echo "======================================"
echo "        Installation Complete!        "
echo "======================================"
echo "VidSimp is now installed in $INSTALL_DIR."
echo "You can launch it from your Desktop Mode application menu under 'Multimedia' or 'VidSimp'."
echo "To use it in Gaming Mode, simply add '$INSTALL_DIR/launch.sh' to Steam as a Non-Steam Game!"
