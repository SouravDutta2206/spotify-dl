#!/usr/bin/env bash

# Exit immediately if a command fails during setup, but handle checks gracefully.
set -eo pipefail

# ANSI color codes for premium terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Helper logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

echo -e "${CYAN}"
echo "=================================================="
echo "          spotify-dl Installer Tool               "
echo "=================================================="
echo -e "${NC}"

# 1. OS check - assume Debian-based with apt-get
if [ ! -f /etc/debian_version ] && ! command -v apt-get &>/dev/null; then
    log_error "This script is designed for Debian-based Linux distributions using the 'apt' package manager."
    exit 1
fi

# 2. Determine root privileges / sudo usage
if [ "$EUID" -ne 0 ]; then
    if command -v sudo &>/dev/null; then
        SUDO="sudo"
    else
        log_error "This script requires root privileges to install packages, but you are not running as root and 'sudo' is not installed."
        exit 1
    fi
else
    SUDO=""
fi

# 3. Check/Install Python 3 (preferably >= 3.11)
INSTALL_PYTHON=false
if command -v python3 &>/dev/null; then
    PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    major=$(echo "$PYTHON_VERSION" | cut -d. -f1)
    minor=$(echo "$PYTHON_VERSION" | cut -d. -f2)
    
    if [ "$major" -lt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -lt 11 ]; }; then
        log_warning "Found Python $PYTHON_VERSION, but version 3.11+ is preferred/required."
        INSTALL_PYTHON=true
    else
        log_info "Python $PYTHON_VERSION is already installed (meets requirements)."
        # Ensure python3-venv is installed as pipx relies on it
        if ! python3 -c "import venv" &>/dev/null; then
            log_warning "Python 3 is installed, but the 'venv' module is missing."
            log_info "Installing python3-venv..."
            $SUDO apt-get update
            $SUDO apt-get install -y python3-venv || {
                log_error "Failed to install python3-venv. pipx requires the venv module to function."
                exit 1
            }
        fi
    fi
else
    log_info "Python 3 is not installed."
    INSTALL_PYTHON=true
fi

if [ "$INSTALL_PYTHON" = true ]; then
    log_info "Installing Python (preferably 3.11)..."
    $SUDO apt-get update
    if $SUDO apt-get install -y python3.11 python3.11-venv python3.11-dev; then
        log_success "Successfully installed Python 3.11 and venv."
    else
        log_warning "Failed to install python3.11. Attempting default python3..."
        $SUDO apt-get install -y python3 python3-venv python3-dev || {
            log_error "Failed to install Python 3."
            exit 1
        }
        log_success "Successfully installed default Python 3."
    fi
fi

# 4. Check/Install Node.js 20+
INSTALL_NODE=false
if command -v node &>/dev/null; then
    NODE_VERSION=$(node -v | cut -d'v' -f2)
    NODE_MAJOR=$(echo "$NODE_VERSION" | cut -d'.' -f1)
    if [ "$NODE_MAJOR" -ge 20 ] 2>/dev/null; then
        log_info "Node.js version $NODE_VERSION (>= 20) is already installed."
    else
        log_warning "Found Node.js version $NODE_VERSION, but Node.js 20+ is preferred/required."
        INSTALL_NODE=true
    fi
else
    log_info "Node.js is not installed."
    INSTALL_NODE=true
fi

if [ "$INSTALL_NODE" = true ]; then
    log_info "Installing Node.js 20..."
    # Ensure curl is installed first
    if ! command -v curl &>/dev/null; then
        log_info "Installing curl..."
        $SUDO apt-get update
        $SUDO apt-get install -y curl
    fi
    
    # Configure NodeSource repository for Node.js 20 and install
    if curl -fsSL https://deb.nodesource.com/setup_20.x | $SUDO -E bash -; then
        if $SUDO apt-get install -y nodejs; then
            log_success "Successfully installed Node.js $(node -v)."
        else
            log_error "Failed to install nodejs package."
            exit 1
        fi
    else
        log_error "Failed to download/configure NodeSource repository for Node.js 20."
        exit 1
    fi
fi

# 5. Check/Install pipx
if command -v pipx &>/dev/null; then
    log_info "pipx is already installed."
else
    log_info "pipx is not installed. Installing pipx..."
    # Try apt installation first
    if $SUDO apt-get install -y pipx; then
        log_success "Successfully installed pipx via apt."
    else
        log_warning "Failed to install pipx via apt. Attempting to install via python3-pip..."
        if ! command -v pip3 &>/dev/null; then
            log_info "Installing python3-pip..."
            $SUDO apt-get install -y python3-pip || {
                log_error "Failed to install python3-pip."
                exit 1
            }
        fi
        python3 -m pip install --user pipx || {
            log_error "Failed to install pipx via pip."
            exit 1
        }
        log_success "Successfully installed pipx via pip."
    fi
fi

# Ensure pipx-installed binaries are available in PATH
pipx ensurepath --force >/dev/null || true
export PATH="$HOME/.local/bin:$PATH"

# 6. Check/Install ffmpeg (required for audio downloading and conversion)
if command -v ffmpeg &>/dev/null; then
    log_info "ffmpeg is already installed."
else
    log_info "ffmpeg is required for downloading and tagging media. Installing ffmpeg..."
    $SUDO apt-get update
    $SUDO apt-get install -y ffmpeg || log_warning "Failed to install ffmpeg automatically. You will need to install it manually for downloads to work."
fi

# 7. Install spotify-dl using pipx
log_info "Installing/upgrading spotify-dl using pipx..."
# We run pipx list and handle failures gracefully
if pipx list 2>/dev/null | grep -q "spotify-dl"; then
    log_info "spotify-dl is already installed. Running pipx upgrade..."
    pipx upgrade spotify-dl || pipx install --force git+https://github.com/SouravDutta2206/spotify-dl.git
else
    if pipx install git+https://github.com/SouravDutta2206/spotify-dl.git; then
        log_success "spotify-dl has been successfully installed!"
    else
        log_error "Failed to install spotify-dl via pipx."
        exit 1
    fi
fi

# 8. Print setup instructions
echo -e "\n${GREEN}======================================================================${NC}"
echo -e "${GREEN}                  INSTALLATION COMPLETED SUCCESSFULLY!                ${NC}"
echo -e "${GREEN}======================================================================${NC}"
echo -e "spotify-dl has been successfully installed using pipx."
echo -e ""
echo -e "${CYAN}To configure and authenticate spotify-dl, follow these steps:${NC}"
echo -e ""
echo -e "  1. Get Spotify API Credentials:"
echo -e "     Go to https://developer.spotify.com/dashboard, log in, create an app,"
echo -e "     and retrieve your Client ID and Client Secret."
echo -e ""
echo -e "  2. Save your credentials in spotify-dl configuration:"
echo -e "     ${YELLOW}spotify-dl config set client-id <YOUR_CLIENT_ID>${NC}"
echo -e "     ${YELLOW}spotify-dl config set client-secret <YOUR_CLIENT_SECRET>${NC}"
echo -e ""
echo -e "  3. Authenticate with Spotify:"
echo -e "     ${YELLOW}spotify-dl auth login${NC}"
echo -e ""
echo -e "  4. Start downloading tracks, albums, or playlists:"
echo -e "     ${YELLOW}spotify-dl https://open.spotify.com/track/...${NC}"
echo -e ""
echo -e "${YELLOW}IMPORTANT:${NC} If the 'spotify-dl' command is not recognized, please restart"
echo -e "your terminal session or run: ${CYAN}source ~/.bashrc${NC} (or your shell's config file)."
echo -e "${GREEN}======================================================================${NC}\n"

