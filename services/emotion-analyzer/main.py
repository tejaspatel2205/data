import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import defaultdict

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
import torch
from transformers import pipeline, RobertaTokenizerFast, TFRobertaForSequenceClassification
from huggingface_hub import login
import logging

from config import (
    API_HOST, API_PORT, MODEL_NAME, HUGGINGFACE_TOKEN, 
    CACHE_TTL, EMOTION_LABELS, EMOTION_COLORS
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="Emotion Analyzer Service", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
api_key_header = APIKeyHeader(name="X-API-Key")

# Models and cache
emotion_pipeline = None
emotion_cache = {}
speaker_emotions = defaultdict(list)

class EmotionRequest(BaseModel):
    text: str
    speaker: Optional[str] = None
    timestamp: Optional[str] = None

class EmotionAnalysisRequest(BaseModel):
    segments: List[Dict]
    meeting_id: Optional[str] = None

class EmotionResponse(BaseModel):
    emotion: str
    confidence: float
    emoji: str
    color: str
    timestamp: str

class SpeakerEmotionResponse(BaseModel):
    speaker: str
    emotions: List[EmotionResponse]
    dominant_emotion: str
    emotion_distribution: Dict[str, float]

class MeetingEmotionResponse(BaseModel):
    meeting_id: Optional[str]
    speakers: List[SpeakerEmotionResponse]
    overall_mood: Dict[str, float]
    emotion_timeline: List[Dict]

def get_emotion_label(text: str) -> Dict:
    """Get emotion analysis for a given text."""
    try:
        if not text or not text.strip():
            return {
                'emotion': 'neutral',
                'confidence': 0.0,
                'emoji': EMOTION_LABELS.get('neutral', '😐'),
                'color': EMOTION_COLORS.get('neutral', '#9CA3AF')
            }
        
        # Check cache first
        cache_key = hash(text.strip().lower())
        if cache_key in emotion_cache:
            cache_data = emotion_cache[cache_key]
            if time.time() - cache_data['timestamp'] < CACHE_TTL:
                return cache_data['result']
        
        # Analyze emotion
        if emotion_pipeline:
            result = emotion_pipeline(text)
            if result and len(result) > 0:
                emotion_data = result[0]
                emotion = emotion_data['label'].lower()
                confidence = emotion_data['score']
                
                result_dict = {
                    'emotion': emotion,
                    'confidence': confidence,
                    'emoji': EMOTION_LABELS.get(emotion, '😐'),
                    'color': EMOTION_COLORS.get(emotion, '#9CA3AF')
                }
                
                # Cache the result
                emotion_cache[cache_key] = {
                    'result': result_dict,
                    'timestamp': time.time()
                }
                
                return result_dict
    except Exception as e:
        logger.error(f"Error analyzing emotion: {str(e)}")
    
    # Fallback
    return {
        'emotion': 'neutral',
        'confidence': 0.0,
        'emoji': EMOTION_LABELS.get('neutral', '😐'),
        'color': EMOTION_COLORS.get('neutral', '#9CA3AF')
    }

async def initialize_model():
    """Initialize the emotion analysis model."""
    global emotion_pipeline
    try:
        logger.info("Initializing emotion analysis model...")
        
        # Login to Hugging Face if token is provided
        if HUGGINGFACE_TOKEN:
            login(HUGGINGFACE_TOKEN)
            logger.info("Logged in to Hugging Face")
        
        # Initialize tokenizer and model
        tokenizer = RobertaTokenizerFast.from_pretrained(MODEL_NAME)
        model = TFRobertaForSequenceClassification.from_pretrained(MODEL_NAME)
        
        # Create pipeline
        emotion_pipeline = pipeline(
            'sentiment-analysis', 
            model=model, 
            tokenizer=tokenizer, 
            framework='tf',
            return_all_scores=False
        )
        
        logger.info("Emotion analysis model initialized successfully")
        
        # Test the model
        test_result = get_emotion_label("I am happy")
        logger.info(f"Model test result: {test_result}")
        
    except Exception as e:
        logger.error(f"Failed to initialize emotion model: {str(e)}")
        raise

@app.on_event("startup")
async def startup_event():
    """Initialize the model on startup."""
    await initialize_model()

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "model_loaded": emotion_pipeline is not None,
        "timestamp": datetime.now().isoformat()
    }

@app.post("/analyze", response_model=EmotionResponse)
async def analyze_emotion(request: EmotionRequest, api_key: str = Depends(api_key_header)):
    """Analyze emotion for a single text."""
    try:
        result = get_emotion_label(request.text)
        
        # Store speaker emotion if speaker is provided
        if request.speaker:
            emotion_data = EmotionResponse(
                emotion=result['emotion'],
                confidence=result['confidence'],
                emoji=result['emoji'],
                color=result['color'],
                timestamp=request.timestamp or datetime.now().isoformat()
            )
            speaker_emotions[request.speaker].append(emotion_data)
            
            # Keep only last 100 emotions per speaker
            if len(speaker_emotions[request.speaker]) > 100:
                speaker_emotions[request.speaker] = speaker_emotions[request.speaker][-100:]
        
        return EmotionResponse(
            emotion=result['emotion'],
            confidence=result['confidence'],
            emoji=result['emoji'],
            color=result['color'],
            timestamp=request.timestamp or datetime.now().isoformat()
        )
    
    except Exception as e:
        logger.error(f"Error in analyze_emotion: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/analyze-meeting", response_model=MeetingEmotionResponse)
async def analyze_meeting_emotions(request: EmotionAnalysisRequest, api_key: str = Depends(api_key_header)):
    """Analyze emotions for all segments in a meeting."""
    try:
        speaker_emotion_data = defaultdict(list)
        emotion_timeline = []
        overall_emotions = defaultdict(int)
        
        # Process each segment
        for segment in request.segments:
            text = segment.get('text', '').strip()
            speaker = segment.get('speaker', 'Unknown')
            timestamp = segment.get('time', datetime.now().isoformat())
            
            if text:
                result = get_emotion_label(text)
                
                emotion_response = EmotionResponse(
                    emotion=result['emotion'],
                    confidence=result['confidence'],
                    emoji=result['emoji'],
                    color=result['color'],
                    timestamp=timestamp
                )
                
                speaker_emotion_data[speaker].append(emotion_response)
                
                # Add to timeline
                emotion_timeline.append({
                    'speaker': speaker,
                    'timestamp': timestamp,
                    'emotion': result['emotion'],
                    'confidence': result['confidence'],
                    'text_preview': text[:50] + "..." if len(text) > 50 else text
                })
                
                # Count overall emotions
                overall_emotions[result['emotion']] += 1
        
        # Calculate emotion distributions and dominant emotions
        speakers_response = []
        for speaker, emotions in speaker_emotion_data.items():
            if emotions:
                # Calculate emotion distribution
                emotion_counts = defaultdict(int)
                for emotion in emotions:
                    emotion_counts[emotion.emotion] += 1
                
                total_emotions = len(emotions)
                emotion_distribution = {
                    emotion: count / total_emotions 
                    for emotion, count in emotion_counts.items()
                }
                
                # Find dominant emotion
                dominant_emotion = max(emotion_counts.items(), key=lambda x: x[1])[0]
                
                speakers_response.append(SpeakerEmotionResponse(
                    speaker=speaker,
                    emotions=emotions[-10:],  # Last 10 emotions
                    dominant_emotion=dominant_emotion,
                    emotion_distribution=emotion_distribution
                ))
        
        # Calculate overall mood
        total_overall = sum(overall_emotions.values())
        overall_mood = {
            emotion: count / total_overall if total_overall > 0 else 0
            for emotion, count in overall_emotions.items()
        }
        
        return MeetingEmotionResponse(
            meeting_id=request.meeting_id,
            speakers=speakers_response,
            overall_mood=overall_mood,
            emotion_timeline=emotion_timeline[-50:]  # Last 50 emotion events
        )
    
    except Exception as e:
        logger.error(f"Error in analyze_meeting_emotions: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/speaker/{speaker_name}/emotions")
async def get_speaker_emotions(speaker_name: str, api_key: str = Depends(api_key_header)):
    """Get emotion history for a specific speaker."""
    try:
        emotions = speaker_emotions.get(speaker_name, [])
        
        if not emotions:
            return {
                "speaker": speaker_name,
                "emotions": [],
                "dominant_emotion": "neutral",
                "emotion_distribution": {}
            }
        
        # Calculate emotion distribution
        emotion_counts = defaultdict(int)
        for emotion in emotions:
            emotion_counts[emotion.emotion] += 1
        
        total_emotions = len(emotions)
        emotion_distribution = {
            emotion: count / total_emotions 
            for emotion, count in emotion_counts.items()
        }
        
        # Find dominant emotion
        dominant_emotion = max(emotion_counts.items(), key=lambda x: x[1])[0]
        
        return {
            "speaker": speaker_name,
            "emotions": emotions[-20:],  # Last 20 emotions
            "dominant_emotion": dominant_emotion,
            "emotion_distribution": emotion_distribution
        }
    
    except Exception as e:
        logger.error(f"Error getting speaker emotions: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/emotions/labels")
async def get_emotion_labels():
    """Get available emotion labels with their emojis and colors."""
    return {
        "labels": EMOTION_LABELS,
        "colors": EMOTION_COLORS
    }

@app.delete("/cache/clear")
async def clear_cache(api_key: str = Depends(api_key_header)):
    """Clear the emotion analysis cache."""
    global emotion_cache, speaker_emotions
    emotion_cache.clear()
    speaker_emotions.clear()
    return {"message": "Cache cleared successfully"}

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=API_HOST,
        port=API_PORT,
        reload=True,
        log_level="info"
    )