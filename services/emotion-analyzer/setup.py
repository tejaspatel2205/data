#!/usr/bin/env python3
"""
Setup script for Emotion Analyzer Service
"""

import subprocess
import sys
import os
from pathlib import Path

def install_requirements():
    """Install required packages."""
    print("Installing required packages...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

def setup_environment():
    """Setup environment variables."""
    env_file = Path(".env")
    if not env_file.exists():
        print("Creating .env file...")
        with open(env_file, "w") as f:
            f.write("""# Emotion Analyzer Service Configuration
# Copy your Hugging Face token here (optional, but recommended for better model access)
HUGGINGFACE_TOKEN=your_token_here

# API Configuration
EMOTION_API_PORT=18060
EMOTION_API_HOST=0.0.0.0

# Cache Configuration (in seconds)
EMOTION_CACHE_TTL=300
""")
        print(".env file created. Please update HUGGINGFACE_TOKEN with your token from https://huggingface.co/settings/tokens")

def download_model():
    """Download the EmoRoBERTa model."""
    print("Downloading EmoRoBERTa model...")
    try:
        from transformers import RobertaTokenizerFast, TFRobertaForSequenceClassification
        tokenizer = RobertaTokenizerFast.from_pretrained("arpanghoshal/EmoRoBERTa")
        model = TFRobertaForSequenceClassification.from_pretrained("arpanghoshal/EmoRoBERTa")
        print("Model downloaded successfully!")
    except Exception as e:
        print(f"Error downloading model: {e}")
        print("The model will be downloaded on first run.")

def main():
    """Main setup function."""
    print("Setting up Emotion Analyzer Service...")
    
    # Install requirements
    try:
        install_requirements()
    except subprocess.CalledProcessError as e:
        print(f"Error installing requirements: {e}")
        sys.exit(1)
    
    # Setup environment
    setup_environment()
    
    # Download model
    download_model()
    
    print("\nSetup complete!")
    print("To run the service:")
    print("  python main.py")
    print("\nOr with custom configuration:")
    print("  EMOTION_API_PORT=18061 python main.py")

if __name__ == "__main__":
    main()