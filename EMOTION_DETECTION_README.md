# Real-time Emotion Detection Integration

This integration adds comprehensive emotion analysis capabilities to your Vexa meeting transcription system. It uses the EmoRoBERTa model for accurate emotion detection and provides real-time visualization in the UI.

## Features

### 🎭 Real-time Emotion Analysis
- Analyzes emotions of speakers in real-time as they speak
- Shows emotion indicators next to speaker names in transcripts
- Updates participant panels with current emotional states

### 📊 Emotion Visualization
- **Overall Meeting Mood**: Displays the dominant emotion with confidence score
- **Emotion Timeline**: Shows chronological emotion changes during the meeting
- **Speaker Insights**: Per-speaker emotion analysis and statistics
- **Sentiment Distribution**: Visual bars showing emotion percentages
- **Top Emotions**: Most frequent emotions as interactive chips

### 🔧 Configurable Settings
- Toggle emotion analysis on/off during meetings
- Cached results for performance optimization
- Supports 28+ different emotion categories

## Architecture

```
UI Frontend (JavaScript)
       ↓
API Gateway (Python FastAPI)
       ↓
Emotion Analyzer Service (Python FastAPI + Transformers)
       ↓
EmoRoBERTa Model (Hugging Face)
```

## Installation & Setup

### 1. Install Emotion Analyzer Service

Navigate to the emotion analyzer service directory:

```bash
cd services/emotion-analyzer
```

Run the setup script:

```bash
python setup.py
```

This will:
- Install required Python packages
- Create environment configuration
- Download the EmoRoBERTa model (optional pre-download)

### 2. Configure Hugging Face Token (Recommended)

1. Get a token from [Hugging Face](https://huggingface.co/settings/tokens)
2. Update the `.env` file in `services/emotion-analyzer/`:

```env
HUGGINGFACE_TOKEN=hf_your_actual_token_here
```

### 3. Update API Gateway Configuration

Add the emotion analyzer URL to your API gateway environment:

```env
EMOTION_ANALYZER_URL=http://localhost:18060
```

### 4. Start Services

#### Start Emotion Analyzer Service:
```bash
cd services/emotion-analyzer
python main.py
```

The service will start on port 18060 by default.

#### Update API Gateway:
Make sure your API gateway includes the updated `main.py` with emotion endpoints.

## Usage

### In the Web UI

1. **Enable Emotion Analysis**: Check the "Enable Real-time Emotions" checkbox in the left panel
2. **Start Meeting**: Send a bot to your meeting as usual
3. **View Emotions**: 
   - See emotion emojis next to speaker names in transcripts
   - Monitor overall meeting mood in the left panel
   - Check emotion timeline in the right panel
   - Analyze emotion distribution and insights

### API Endpoints

The following new endpoints are available:

#### Get Meeting Emotions
```http
GET /analysis/emotions/{platform}/{meeting_id}
```

#### Get Speaker Emotions
```http
GET /analysis/emotion/{platform}/{meeting_id}/{speaker_name}
```

#### Analyze Text Emotion
```http
POST /analysis/emotion/text
Content-Type: application/json

{
  "text": "I'm feeling great about this project!",
  "speaker": "John Doe",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

#### Get Emotion Labels
```http
GET /analysis/emotions/labels
```

## Supported Emotions

The system recognizes 28+ emotions including:

- **Positive**: joy, amusement, admiration, approval, excitement, gratitude, love, optimism, pride, relief
- **Negative**: anger, annoyance, disappointment, disgust, fear, grief, sadness, remorse
- **Neutral**: neutral, surprise, curiosity, confusion, realization
- **Complex**: caring, desire, embarrassment, nervousness

Each emotion is displayed with:
- 🎭 Emoji representation
- 🎨 Color coding
- 📊 Confidence percentage

## Performance Considerations

### Caching
- Emotion results are cached for 5 minutes by default
- Identical text won't be re-analyzed during cache period
- Cache can be cleared via API endpoint

### Model Loading
- EmoRoBERTa model loads on first request (may take 30-60 seconds)
- Subsequent requests are fast (~100-200ms)
- Model stays in memory for better performance

### Optimization Tips
- Use shorter text snippets for faster analysis
- Enable emotion analysis only when needed
- Consider running emotion service on GPU for better performance

## Troubleshooting

### Common Issues

#### 1. Model Download Fails
```
Error: Failed to download model
```
**Solution**: Check internet connection and Hugging Face token. Model will auto-download on first use.

#### 2. Emotion Service Unavailable
```
Error: Emotion analysis service unavailable
```
**Solution**: Ensure emotion analyzer service is running on port 18060.

#### 3. API Gateway Connection Error
```
Error: 503 Service unavailable
```
**Solution**: Update `EMOTION_ANALYZER_URL` environment variable in API gateway.

#### 4. Empty Emotion Results
```
No emotions detected yet
```
**Solution**: Wait for speakers to say something. Very short phrases may not generate emotions.

### Debug Mode

Enable debug logging in the emotion analyzer:

```python
# In main.py
logging.basicConfig(level=logging.DEBUG)
```

## Configuration Options

### Emotion Analyzer Service (`services/emotion-analyzer/.env`)

```env
# Required for optimal model access
HUGGINGFACE_TOKEN=your_token_here

# API Configuration
EMOTION_API_PORT=18060
EMOTION_API_HOST=0.0.0.0

# Performance tuning
EMOTION_CACHE_TTL=300  # Cache duration in seconds
```

### UI Configuration

```javascript
// In app.js - customize emotion update frequency
const EMOTION_UPDATE_INTERVAL = 3000; // milliseconds

// Enable/disable emotion features
const EMOTION_FEATURES = {
  realTimeUpdates: true,
  speakerBadges: true,
  emotionTimeline: true,
  analytics: true
};
```

## Advanced Usage

### Custom Emotion Analysis

You can analyze any text using the API:

```javascript
// Analyze custom text
const analyzeEmotion = async (text) => {
  const response = await fetch('/analysis/emotion/text', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': API_TOKEN
    },
    body: JSON.stringify({
      text: text,
      speaker: 'Custom User',
      timestamp: new Date().toISOString()
    })
  });
  
  const emotion = await response.json();
  console.log('Detected emotion:', emotion);
};
```

### Bulk Analysis

For analyzing multiple texts at once:

```javascript
const analyzeMeeting = async (segments) => {
  const response = await fetch('/analysis/emotions/meeting', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': API_TOKEN
    },
    body: JSON.stringify({
      segments: segments,
      meeting_id: 'meeting-123'
    })
  });
  
  const analysis = await response.json();
  console.log('Meeting analysis:', analysis);
};
```

## Integration Examples

### React Component Example

```jsx
import React, { useState, useEffect } from 'react';

const EmotionIndicator = ({ speaker, text }) => {
  const [emotion, setEmotion] = useState(null);
  
  useEffect(() => {
    const analyzeEmotion = async () => {
      const response = await fetch('/analysis/emotion/text', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, speaker })
      });
      const result = await response.json();
      setEmotion(result);
    };
    
    if (text) analyzeEmotion();
  }, [text, speaker]);
  
  return (
    <div className="emotion-indicator">
      {emotion && (
        <>
          <span className="emotion-emoji">{emotion.emoji}</span>
          <span className="emotion-label">{emotion.emotion}</span>
        </>
      )}
    </div>
  );
};
```

## Contributing

To extend the emotion detection system:

1. **Add New Emotions**: Update `EMOTION_LABELS` and `EMOTION_COLORS` in `config.py`
2. **Custom Models**: Replace EmoRoBERTa with your preferred model in `main.py`
3. **UI Enhancements**: Add new visualization components in the UI
4. **API Extensions**: Add new endpoints for specific use cases

## License

This emotion detection integration uses:
- **EmoRoBERTa**: Apache 2.0 License
- **Transformers**: Apache 2.0 License  
- **FastAPI**: MIT License

---

For questions or support, check the main Vexa documentation or create an issue in the repository.