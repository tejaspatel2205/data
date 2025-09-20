import os
from dotenv import load_dotenv

load_dotenv()

# API Configuration
API_PORT = int(os.getenv("EMOTION_API_PORT", "18060"))
API_HOST = os.getenv("EMOTION_API_HOST", "0.0.0.0")

# Model Configuration
MODEL_NAME = "arpanghoshal/EmoRoBERTa"
HUGGINGFACE_TOKEN = os.getenv("HUGGINGFACE_TOKEN", "")

# Cache Configuration
CACHE_TTL = int(os.getenv("EMOTION_CACHE_TTL", "300"))  # 5 minutes

# Emotion Labels Mapping
EMOTION_LABELS = {
    'admiration': '😊',
    'amusement': '😄',
    'anger': '😠',
    'annoyance': '😤',
    'approval': '👍',
    'caring': '🤗',
    'confusion': '😕',
    'curiosity': '🤔',
    'desire': '😍',
    'disappointment': '😞',
    'disapproval': '👎',
    'disgust': '🤢',
    'embarrassment': '😳',
    'excitement': '🎉',
    'fear': '😨',
    'gratitude': '🙏',
    'grief': '😢',
    'joy': '😊',
    'love': '❤️',
    'nervousness': '😰',
    'optimism': '😌',
    'pride': '😎',
    'realization': '💡',
    'relief': '😅',
    'remorse': '😔',
    'sadness': '😢',
    'surprise': '😲',
    'neutral': '😐'
}

# Emotion Colors for UI
EMOTION_COLORS = {
    'admiration': '#10B981',
    'amusement': '#F59E0B',
    'anger': '#EF4444',
    'annoyance': '#F97316',
    'approval': '#10B981',
    'caring': '#EC4899',
    'confusion': '#8B5CF6',
    'curiosity': '#06B6D4',
    'desire': '#EF4444',
    'disappointment': '#6B7280',
    'disapproval': '#EF4444',
    'disgust': '#84CC16',
    'embarrassment': '#F97316',
    'excitement': '#F59E0B',
    'fear': '#6366F1',
    'gratitude': '#10B981',
    'grief': '#374151',
    'joy': '#F59E0B',
    'love': '#EC4899',
    'nervousness': '#8B5CF6',
    'optimism': '#10B981',
    'pride': '#F59E0B',
    'realization': '#06B6D4',
    'relief': '#10B981',
    'remorse': '#6B7280',
    'sadness': '#374151',
    'surprise': '#F59E0B',
    'neutral': '#9CA3AF'
}