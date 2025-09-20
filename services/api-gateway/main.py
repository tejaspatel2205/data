import uvicorn
from fastapi import FastAPI, Request, Response, HTTPException, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.security import APIKeyHeader
import httpx
import os
from dotenv import load_dotenv
import json # For request body processing
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional

# Import schemas for documentation
from shared_models.schemas import (
    MeetingCreate, MeetingResponse, MeetingListResponse, MeetingDataUpdate, # Updated/Added Schemas
    TranscriptionResponse, TranscriptionSegment,
    UserCreate, UserResponse, TokenResponse, UserDetailResponse, # Admin Schemas
    ErrorResponse,
    Platform, # Import Platform enum for path parameters
    BotStatusResponse # ADDED: Import response model for documentation
)

load_dotenv()

# Configuration - Service endpoints are now mandatory environment variables
ADMIN_API_URL = os.getenv("ADMIN_API_URL")
BOT_MANAGER_URL = os.getenv("BOT_MANAGER_URL")
TRANSCRIPTION_COLLECTOR_URL = os.getenv("TRANSCRIPTION_COLLECTOR_URL")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
EMOTION_ANALYZER_URL = os.getenv("EMOTION_ANALYZER_URL", "http://localhost:18060")

# --- Validation at startup ---
if not all([ADMIN_API_URL, BOT_MANAGER_URL, TRANSCRIPTION_COLLECTOR_URL]):
    missing_vars = [
        var_name
        for var_name, var_value in {
            "ADMIN_API_URL": ADMIN_API_URL,
            "BOT_MANAGER_URL": BOT_MANAGER_URL,
            "TRANSCRIPTION_COLLECTOR_URL": TRANSCRIPTION_COLLECTOR_URL,
        }.items()
        if not var_value
    ]
    raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
    
# Log the Emotion Analyzer URL    
logger = logging.getLogger("api_gateway")
logger.info(f"Using Emotion Analyzer at: {EMOTION_ANALYZER_URL}")

# Response Models
# class BotResponseModel(BaseModel): ...
# class MeetingModel(BaseModel): ...
# class MeetingsResponseModel(BaseModel): ...
# class TranscriptSegmentModel(BaseModel): ...
# class TranscriptResponseModel(BaseModel): ...
# class UserModel(BaseModel): ...
# class TokenModel(BaseModel): ...

# Security Schemes for OpenAPI
api_key_scheme = APIKeyHeader(name="X-API-Key", description="API Key for client operations", auto_error=False)
admin_api_key_scheme = APIKeyHeader(name="X-Admin-API-Key", description="API Key for admin operations", auto_error=False)

app = FastAPI(
    title="Vexa API Gateway",
    description="""
    **Main entry point for the Vexa platform APIs.**
    
    Provides access to:
    - Bot Management (Starting/Stopping transcription bots)
    - Transcription Retrieval
    - User & Token Administration (Admin only)
    
    ## Authentication
    
    Two types of API keys are used:
    
    1.  **`X-API-Key`**: Required for all regular client operations (e.g., managing bots, getting transcripts). Obtain your key from an administrator.
    2.  **`X-Admin-API-Key`**: Required *only* for administrative endpoints (prefixed with `/admin`). This key is configured server-side.
    
    Include the appropriate header in your requests.
    """,
    version="1.2.0", # Incremented version
    contact={
        "name": "Vexa Support",
        "url": "https://vexa.io/support", # Placeholder URL
        "email": "support@vexa.io", # Placeholder Email
    },
    license_info={
        "name": "Proprietary",
    },
    # Include security schemes in OpenAPI spec
    # Note: Applying them globally or per-route is done below
)

# Custom OpenAPI Schema
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    # Generate basic schema first, without components
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        contact=app.contact,
        license_info=app.license_info,
    )
    
    # Manually add security schemes to the schema
    if "components" not in openapi_schema:
        openapi_schema["components"] = {}
    
    # Add securitySchemes component
    openapi_schema["components"]["securitySchemes"] = {
        "ApiKeyAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "API Key for client operations"
        },
        "AdminApiKeyAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "X-Admin-API-Key",
            "description": "API Key for admin operations"
        }
    }
    
    # Optional: Add global security requirement
    # openapi_schema["security"] = [{"ApiKeyAuth": []}]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- HTTP Client --- 
# Use a single client instance for connection pooling
@app.on_event("startup")
async def startup_event():
    app.state.http_client = httpx.AsyncClient()

@app.on_event("shutdown")
async def shutdown_event():
    await app.state.http_client.aclose()

# --- Helper for Forwarding --- 
async def forward_request(client: httpx.AsyncClient, method: str, url: str, request: Request) -> Response:
    # Copy original headers, converting to a standard dict
    # Exclude host, content-length, transfer-encoding as they are handled by httpx/server
    excluded_headers = {"host", "content-length", "transfer-encoding"}
    headers = {k.lower(): v for k, v in request.headers.items() if k.lower() not in excluded_headers}
    
    # Debug logging for original request headers
    print(f"DEBUG: Original request headers: {dict(request.headers)}")
    print(f"DEBUG: Original query params: {dict(request.query_params)}")
    
    # Determine target service based on URL path prefix
    is_admin_request = url.startswith(f"{ADMIN_API_URL}/admin")
    
    # Forward appropriate auth header if present
    if is_admin_request:
        admin_key = request.headers.get("x-admin-api-key")
        if admin_key:
            headers["x-admin-api-key"] = admin_key
            print(f"DEBUG: Forwarding x-admin-api-key header")
        else:
            print(f"DEBUG: No x-admin-api-key header found in request")
    else:
        # Forward client API key for bot-manager and transcription-collector
        client_key = request.headers.get("x-api-key")
        if client_key:
            headers["x-api-key"] = client_key
            print(f"DEBUG: Forwarding x-api-key header: {client_key[:5]}...")
        else:
            print(f"DEBUG: No x-api-key header found in request. Headers: {dict(request.headers)}")
    
    # Debug logging for forwarded headers
    print(f"DEBUG: Forwarded headers: {headers}")
    
    # Forward query parameters
    forwarded_params = dict(request.query_params)
    if forwarded_params:
        print(f"DEBUG: Forwarding query params: {forwarded_params}")
    
    content = await request.body()
    
    try:
        print(f"DEBUG: Forwarding {method} request to {url}")
        resp = await client.request(method, url, headers=headers, params=forwarded_params or None, content=content)
        print(f"DEBUG: Response from {url}: status={resp.status_code}")
        # Return downstream response directly (including headers, status code)
        return Response(content=resp.content, status_code=resp.status_code, headers=dict(resp.headers))
    except httpx.RequestError as exc:
        print(f"DEBUG: Request error: {exc}")
        raise HTTPException(status_code=503, detail=f"Service unavailable: {exc}")

# --- Root Endpoint --- 
@app.get("/", tags=["General"], summary="API Gateway Root")
async def root():
    """Provides a welcome message for the Vexa API Gateway."""
    return {"message": "Welcome to the Vexa API Gateway"}

# --- Bot Manager Routes --- 
@app.post("/bots",
         tags=["Bot Management"],
         summary="Request a new bot to join a meeting",
         description="Creates a new meeting record and launches a bot instance based on platform and native meeting ID.",
         # response_model=MeetingResponse, # Response comes from downstream, keep commented
         status_code=status.HTTP_201_CREATED,
         dependencies=[Depends(api_key_scheme)],
         # Explicitly define the request body schema for OpenAPI documentation
         openapi_extra={
             "requestBody": {
                 "content": {
                     "application/json": {
                         "schema": MeetingCreate.schema()
                     }
                 },
                 "required": True,
                 "description": "Specify the meeting platform, native ID, and optional bot name."
             },
         })
# Function signature remains generic for forwarding
async def request_bot_proxy(request: Request): 
    """Forward request to Bot Manager to start a bot."""
    url = f"{BOT_MANAGER_URL}/bots"
    # forward_request handles reading and passing the body from the original request
    return await forward_request(app.state.http_client, "POST", url, request)

@app.delete("/bots/{platform}/{native_meeting_id}",
           tags=["Bot Management"],
           summary="Stop a bot for a specific meeting",
           description="Stops the bot container associated with the specified platform and native meeting ID. Requires ownership via API key.",
           response_model=MeetingResponse,
           dependencies=[Depends(api_key_scheme)])
async def stop_bot_proxy(platform: Platform, native_meeting_id: str, request: Request):
    """Forward request to Bot Manager to stop a bot."""
    url = f"{BOT_MANAGER_URL}/bots/{platform.value}/{native_meeting_id}"
    return await forward_request(app.state.http_client, "DELETE", url, request)

# --- ADD Route for PUT /bots/.../config ---
@app.put("/bots/{platform}/{native_meeting_id}/config",
          tags=["Bot Management"],
          summary="Update configuration for an active bot",
          description="Updates the language and/or task for an active bot. Sends command via Bot Manager.",
          status_code=status.HTTP_202_ACCEPTED,
          dependencies=[Depends(api_key_scheme)])
# Need to accept request body for PUT
async def update_bot_config_proxy(platform: Platform, native_meeting_id: str, request: Request): 
    """Forward request to Bot Manager to update bot config."""
    url = f"{BOT_MANAGER_URL}/bots/{platform.value}/{native_meeting_id}/config"
    # forward_request handles reading and passing the body from the original request
    return await forward_request(app.state.http_client, "PUT", url, request)
# -------------------------------------------

# --- ADD Route for GET /bots/status ---
@app.get("/bots/status",
         tags=["Bot Management"],
         summary="Get status of running bots for the user",
         description="Retrieves a list of currently running bot containers associated with the authenticated user.",
         response_model=BotStatusResponse, # Document expected response
         dependencies=[Depends(api_key_scheme)])
async def get_bots_status_proxy(request: Request):
    """Forward request to Bot Manager to get running bot status."""
    url = f"{BOT_MANAGER_URL}/bots/status"
    return await forward_request(app.state.http_client, "GET", url, request)
# --- END Route for GET /bots/status ---

# --- Transcription Collector Routes --- 
@app.get("/meetings",
        tags=["Transcriptions"],
        summary="Get list of user's meetings",
        description="Returns a list of all meetings initiated by the user associated with the API key.",
        response_model=MeetingListResponse, 
        dependencies=[Depends(api_key_scheme)])
async def get_meetings_proxy(request: Request):
    """Forward request to Transcription Collector to get meetings."""
    url = f"{TRANSCRIPTION_COLLECTOR_URL}/meetings"
    return await forward_request(app.state.http_client, "GET", url, request)

@app.get("/transcripts/{platform}/{native_meeting_id}",
        tags=["Transcriptions"],
        summary="Get transcript for a specific meeting",
        description="Retrieves the transcript segments for a meeting specified by its platform and native ID.",
        response_model=TranscriptionResponse,
        dependencies=[Depends(api_key_scheme)])
async def get_transcript_proxy(platform: Platform, native_meeting_id: str, request: Request):
    """Forward request to Transcription Collector to get a transcript."""
    url = f"{TRANSCRIPTION_COLLECTOR_URL}/transcripts/{platform.value}/{native_meeting_id}"
    return await forward_request(app.state.http_client, "GET", url, request)

@app.patch("/meetings/{platform}/{native_meeting_id}",
           tags=["Transcriptions"],
           summary="Update meeting data",
           description="Updates meeting metadata. Only name, participants, languages, and notes can be updated.",
           response_model=MeetingResponse,
           dependencies=[Depends(api_key_scheme)],
           openapi_extra={
               "requestBody": {
                   "content": {
                       "application/json": {
                           "schema": {
                               "type": "object",
                               "properties": {
                                   "data": MeetingDataUpdate.schema()
                               },
                               "required": ["data"]
                           }
                       }
                   },
                   "required": True,
                   "description": "Meeting data to update (name, participants, languages, notes only)"
               },
           })
async def update_meeting_data_proxy(platform: Platform, native_meeting_id: str, request: Request):
    """Forward request to Transcription Collector to update meeting data."""
    url = f"{TRANSCRIPTION_COLLECTOR_URL}/meetings/{platform.value}/{native_meeting_id}"
    return await forward_request(app.state.http_client, "PATCH", url, request)

@app.delete("/meetings/{platform}/{native_meeting_id}",
            tags=["Transcriptions"],
            summary="Delete meeting and its transcripts",
            description="Deletes a specific meeting and all its associated transcripts. This action cannot be undone.",
            dependencies=[Depends(api_key_scheme)])
async def delete_meeting_proxy(platform: Platform, native_meeting_id: str, request: Request):
    """Forward request to Transcription Collector to delete meeting and its transcripts."""
    url = f"{TRANSCRIPTION_COLLECTOR_URL}/meetings/{platform.value}/{native_meeting_id}"
    return await forward_request(app.state.http_client, "DELETE", url, request)

# --- User Profile Routes ---
@app.put("/user/webhook",
         tags=["User"],
         summary="Set user webhook URL",
         description="Sets a webhook URL for the authenticated user to receive notifications.",
         status_code=status.HTTP_200_OK,
         dependencies=[Depends(api_key_scheme)])
async def set_user_webhook_proxy(request: Request):
    """Forward request to Admin API to set user webhook."""
    url = f"{ADMIN_API_URL}/user/webhook"
    return await forward_request(app.state.http_client, "PUT", url, request)

# --- Admin API Routes --- 
@app.api_route("/admin/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"], 
               tags=["Administration"],
               summary="Forward admin requests",
               description="Forwards requests prefixed with `/admin` to the Admin API service. Requires `X-Admin-API-Key`.",
               dependencies=[Depends(admin_api_key_scheme)])
async def forward_admin_request(request: Request, path: str):
    """Generic forwarder for all admin endpoints."""
    admin_path = f"/admin/{path}" 
    url = f"{ADMIN_API_URL}{admin_path}"
    return await forward_request(app.state.http_client, request.method, url, request)

# ------------------------
# Analysis Endpoints (Summarization, Mood & Emotions)
# ------------------------

STOP_WORDS = {
    "the","and","for","with","that","this","from","have","will","your","ours","you","are","was","but","not","our",
    "their","them","they","she","his","her","him","who","what","when","where","why","how","into","onto","about","over",
    "under","after","before","while","there","here","also","just","like","get","got","been","being","than","then","very"
}

# Small emotion lexicon (keep lightweight)
EMOTION_LEXICON: Dict[str, List[str]] = {
    "joy": ["happy","glad","joy","delight","excited","pleased","thrilled","great","awesome","fantastic"],
    "sadness": ["sad","down","unhappy","upset","depressed","unfortunate","sorry","regret"],
    "anger": ["angry","mad","furious","annoyed","irritated","frustrated"],
    "fear": ["afraid","scared","fear","worried","concerned","anxious"],
    "surprise": ["surprised","amazed","astonished","unexpected"],
    "trust": ["confident","assure","reliable","trust","secure","certain"],
    "disgust": ["disgust","gross","nasty","awful","terrible"],
    "anticipation": ["anticipate","expect","plan","looking","forward","soon"]
}

def _tokenize_words(text: str) -> List[str]:
    import re
    return re.findall(r"[a-zA-Z]{3,}", text.lower())

def _score_sentences_by_tf(segments: List[Dict[str, Any]]) -> List[str]:
    # Use segment texts as candidates; score by term-frequency
    all_text = " ".join((s.get("text") or s.get("content") or "") for s in segments)
    tf: Dict[str, int] = {}
    for w in _tokenize_words(all_text):
        if w in STOP_WORDS:
            continue
        tf[w] = tf.get(w, 0) + 1
    scored: List[Dict[str, Any]] = []
    for s in segments:
        sent = (s.get("text") or s.get("content") or "").strip()
        if not sent:
            continue
        score = 0
        for w in _tokenize_words(sent):
            if w in STOP_WORDS:
                continue
            score += tf.get(w, 0)
        scored.append({"score": score, "sent": sent, "speaker": s.get("speaker", "Speaker"), "time": s.get("time", "")})  
    scored.sort(key=lambda x: x["score"], reverse=True)
    return [x["sent"] for x in scored[:10]]  # Return top 10 most significant sentences

# --- Emotion Analysis Routes --- 
@app.get("/analysis/emotions/{platform}/{native_meeting_id}",
        tags=["Analysis"],
        summary="Get emotion analysis for a meeting",
        description="Retrieves emotion analysis for all speakers in a meeting specified by its platform and native ID.",
        dependencies=[Depends(api_key_scheme)])
async def get_meeting_emotions_proxy(platform: Platform, native_meeting_id: str, request: Request):
    """Forward request to Emotion Analyzer to get meeting emotions."""
    try:
        # First get the transcript
        transcript_url = f"{TRANSCRIPTION_COLLECTOR_URL}/transcripts/{platform.value}/{native_meeting_id}"
        transcript_resp = await app.state.http_client.request(
            "GET",
            transcript_url,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": request.headers.get("x-api-key", "")
            }
        )
        
        if not transcript_resp.is_success:
            return Response(
                content=transcript_resp.content,
                status_code=transcript_resp.status_code,
                headers=dict(transcript_resp.headers)
            )
        
        transcript_data = transcript_resp.json()
        segments = transcript_data.get("segments", []) or (transcript_data.get("data", {}) or {}).get("transcripts", [])
        
        # Send to emotion analyzer
        emotion_url = f"{EMOTION_ANALYZER_URL}/analyze-meeting"
        payload = {
            "segments": segments,
            "meeting_id": f"{platform.value}/{native_meeting_id}"
        }
        
        emotion_resp = await app.state.http_client.request(
            "POST",
            emotion_url,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": request.headers.get("x-api-key", "")
            }
        )
        
        return Response(
            content=emotion_resp.content,
            status_code=emotion_resp.status_code,
            headers=dict(emotion_resp.headers)
        )
    except Exception as e:
        print(f"Error in emotion analysis: {str(e)}")
        raise HTTPException(status_code=503, detail=f"Emotion analysis service unavailable: {str(e)}")

@app.get("/analysis/emotion/{platform}/{native_meeting_id}/{speaker_name}",
        tags=["Analysis"],
        summary="Get emotion analysis for a specific speaker",
        description="Retrieves emotion analysis for a specific speaker in a meeting.",
        dependencies=[Depends(api_key_scheme)])
async def get_speaker_emotion_proxy(platform: Platform, native_meeting_id: str, speaker_name: str, request: Request):
    """Forward request to Emotion Analyzer to get speaker emotions."""
    try:
        # Get speaker emotions
        emotion_url = f"{EMOTION_ANALYZER_URL}/speaker/{speaker_name}/emotions"
        emotion_resp = await app.state.http_client.request(
            "GET",
            emotion_url,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": request.headers.get("x-api-key", "")
            }
        )
        
        return Response(
            content=emotion_resp.content,
            status_code=emotion_resp.status_code,
            headers=dict(emotion_resp.headers)
        )
    except Exception as e:
        print(f"Error getting speaker emotion: {str(e)}")
        raise HTTPException(status_code=503, detail=f"Emotion analysis service unavailable: {str(e)}")

@app.get("/analysis/emotions/labels",
        tags=["Analysis"],
        summary="Get emotion labels",
        description="Retrieves all available emotion labels with their emojis and colors.")
async def get_emotion_labels_proxy(request: Request):
    """Forward request to Emotion Analyzer to get emotion labels."""
    try:
        emotion_url = f"{EMOTION_ANALYZER_URL}/emotions/labels"
        emotion_resp = await app.state.http_client.request(
            "GET",
            emotion_url
        )
        
        return Response(
            content=emotion_resp.content,
            status_code=emotion_resp.status_code,
            headers=dict(emotion_resp.headers)
        )
    except Exception as e:
        print(f"Error getting emotion labels: {str(e)}")
        raise HTTPException(status_code=503, detail=f"Emotion analysis service unavailable: {str(e)}")

@app.post("/analysis/emotion/text",
         tags=["Analysis"],
         summary="Analyze emotion for a text",
         description="Analyzes emotion for a given text.",
         dependencies=[Depends(api_key_scheme)])
async def analyze_text_emotion_proxy(request: Request):
    """Forward request to Emotion Analyzer to analyze text emotion."""
    try:
        emotion_url = f"{EMOTION_ANALYZER_URL}/analyze"
        content = await request.body()
        
        emotion_resp = await app.state.http_client.request(
            "POST",
            emotion_url,
            content=content,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": request.headers.get("x-api-key", "")
            }
        )
        
        return Response(
            content=emotion_resp.content,
            status_code=emotion_resp.status_code,
            headers=dict(emotion_resp.headers)
        )
    except Exception as e:
        print(f"Error analyzing text emotion: {str(e)}")
        raise HTTPException(status_code=503, detail=f"Emotion analysis service unavailable: {str(e)}")

# Regular mood analysis function - kept for backward compatibility
@app.get("/analysis/mood/{platform}/{native_meeting_id}",
        tags=["Analysis"],
        summary="Get simple mood analysis for a meeting",
        description="Retrieves a basic mood analysis based on lexicon matching for each speaker in a meeting.",
        dependencies=[Depends(api_key_scheme)])
async def get_meeting_moods(platform: Platform, native_meeting_id: str, request: Request):
    """Analyze mood of speakers in a meeting using basic lexicon matching."""
    # Try to get emotions from emotion analyzer first
    try:
        emotion_url = f"{EMOTION_ANALYZER_URL}/analyze-meeting"
        transcript_url = f"{TRANSCRIPTION_COLLECTOR_URL}/transcripts/{platform.value}/{native_meeting_id}"
        
        transcript_resp = await app.state.http_client.request(
            "GET", 
            transcript_url,
            headers={"X-API-Key": request.headers.get("x-api-key", "")}
        )
        
        if transcript_resp.is_success:
            transcript_data = transcript_resp.json()
            segments = transcript_data.get("segments", []) or (transcript_data.get("data", {}) or {}).get("transcripts", [])
            
            payload = {
                "segments": segments,
                "meeting_id": f"{platform.value}/{native_meeting_id}"
            }
            
            emotion_resp = await app.state.http_client.request(
                "POST",
                emotion_url,
                json=payload,
                headers={"X-API-Key": request.headers.get("x-api-key", "")}
            )
            
            if emotion_resp.is_success:
                emotion_data = emotion_resp.json()
                mood_response = {"moods": {}}
                
                # Convert emotion analysis format to mood format for backward compatibility
                for speaker in emotion_data.get("speakers", []):
                    speaker_name = speaker.get("speaker")
                    dominant_emotion = speaker.get("dominant_emotion")
                    
                    mood_response["moods"][speaker_name] = {
                        "dominant": dominant_emotion,
                        "score": 0.8  # Default confidence score
                    }
                
                return mood_response
    except Exception as e:
        # Fall back to lexicon-based approach if emotion analysis fails
        print(f"Falling back to lexicon-based mood analysis: {str(e)}")
    
    # Original lexicon-based implementation
    try:
        url = f"{TRANSCRIPTION_COLLECTOR_URL}/transcripts/{platform.value}/{native_meeting_id}"
        
        resp = await app.state.http_client.request(
            "GET", 
            url,
            headers={"X-API-Key": request.headers.get("x-api-key", "")}
        )
        
        if not resp.is_success:
            return Response(content=resp.content, status_code=resp.status_code)
        
        data = resp.json()
        segments = data.get("segments", []) or (data.get("data", {}) or {}).get("transcripts", [])
        
        # Group by speaker
        by_speaker = {}
        for s in segments:
            speaker = s.get("speaker", "Unknown")
            text = s.get("text", "") or s.get("content", "")
            if not speaker in by_speaker:
                by_speaker[speaker] = []
            by_speaker[speaker].append(text)
        
        # Analyze moods by speaker
        moods = {}
        for speaker, texts in by_speaker.items():
            # Join all texts from this speaker
            all_text = " ".join(texts).lower()
            
            # Count emotion words
            emotion_counts = {emotion: 0 for emotion in EMOTION_LEXICON.keys()}
            
            # Simple word-based emotion detection
            words = _tokenize_words(all_text)
            for word in words:
                for emotion, keywords in EMOTION_LEXICON.items():
                    if word in keywords:
                        emotion_counts[emotion] += 1
            
            # Find dominant emotion
            max_count = 0
            dominant = "neutral"
            for emotion, count in emotion_counts.items():
                if count > max_count:
                    max_count = count
                    dominant = emotion
            
            moods[speaker] = {
                "dominant": dominant, 
                "score": 0.7,  # Fixed confidence score for lexicon approach
                "counts": emotion_counts
            }
        
        return {"moods": moods}
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error analyzing moods: {str(e)}"
        )

# Original Summarize endpoints - kept for backward compatibility

def _analyze_emotions_by_speaker(segments: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    # Aggregate counts by speaker
    per_speaker: Dict[str, Dict[str, int]] = {}
    for s in segments:
        speaker = (s.get("speaker") or s.get("speaker_name") or "Speaker").strip()
        text = (s.get("text") or s.get("content") or "").lower()
        if speaker not in per_speaker:
            per_speaker[speaker] = {emo: 0 for emo in EMOTION_LEXICON.keys()}
        for emo, words in EMOTION_LEXICON.items():
            for w in words:
                if w in text:
                    per_speaker[speaker][emo] += 1
    # Convert to label + scores
    result: Dict[str, Dict[str, Any]] = {}
    for speaker, scores in per_speaker.items():
        # Choose dominant emotion
        dominant = max(scores.items(), key=lambda x: x[1])[0] if scores else "neutral"
        result[speaker] = {"dominant": dominant, "scores": scores}
    return result

class SummaryResponse(BaseModel):
    bullets: List[str] = Field(default_factory=list)

class MoodResponse(BaseModel):
    moods: Dict[str, Dict[str, Any]]

async def _fetch_transcript_segments(client: httpx.AsyncClient, platform_value: str, native_meeting_id: str, api_key: str) -> List[Dict[str, Any]]:
    url = f"{TRANSCRIPTION_COLLECTOR_URL}/transcripts/{platform_value}/{native_meeting_id}"
    resp = await client.get(url, headers={"x-api-key": api_key})
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=f"Failed to fetch transcript: {resp.text}")
    data = resp.json()
    segments = data.get("segments") or data.get("data", {}).get("transcripts") or []
    return segments

@app.get("/analysis/summarize/{platform}/{native_meeting_id}",
         tags=["Analysis"],
         summary="Summarize a meeting transcript into bullet points",
         response_model=SummaryResponse,
         dependencies=[Depends(api_key_scheme)])
async def summarize_transcript(platform: Platform, native_meeting_id: str, request: Request):
    api_key = request.headers.get("x-api-key") or ""
    segments = await _fetch_transcript_segments(app.state.http_client, platform.value, native_meeting_id, api_key)
    bullets = _score_sentences_by_tf(segments)
    return SummaryResponse(bullets=bullets)


# ---- Llama (Ollama) powered summarization ----
class LlamaSummaryResponse(BaseModel):
    text: str

def _build_llama_prompt(segments: List[Dict[str, Any]]) -> str:
    # Build a concise prompt with strict formatting expectations
    lines: List[str] = []
    for s in segments:
        speaker = s.get("speaker") or s.get("speaker_name") or "Speaker"
        time = s.get("time") or s.get("start_time") or ""
        text = s.get("text") or s.get("content") or ""
        if text:
            lines.append(f"[{time}] {speaker}: {text}")
    transcript_text = "\n".join(lines)
    # Avoid extremely large payloads (Ollama accepts large, but keep sane)
    if len(transcript_text) > 20000:
        transcript_text = transcript_text[-20000:]
    prompt = (
        "You are an expert meeting analyst. Read the transcript and produce a concise output with the following sections:\n"
        "1) Purpose of the meeting (1-2 lines).\n"
        "2) Key decisions (bullet points, include speaker and time).\n"
        "3) Actionable tasks (bullet points with owners and time if specified).\n"
        "4) Important highlights (bullet points).\n"
        "Format strictly in Markdown using headings and dashes for bullets.\n\n"
        "Transcript:\n" + transcript_text
    )
    return prompt

@app.get("/analysis/summarize_llama/{platform}/{native_meeting_id}",
         tags=["Analysis"],
         summary="Summarize transcript using local Ollama llama3.2:latest",
         response_model=LlamaSummaryResponse,
         dependencies=[Depends(api_key_scheme)])
async def summarize_transcript_llama(platform: Platform, native_meeting_id: str, request: Request):
    api_key = request.headers.get("x-api-key") or ""
    segments = await _fetch_transcript_segments(app.state.http_client, platform.value, native_meeting_id, api_key)
    if not segments:
        return LlamaSummaryResponse(text="# Summary\n\n- No transcript available yet.")
    prompt = _build_llama_prompt(segments)
    payload = {"model": "llama3.2:latest", "prompt": prompt, "stream": False}
    try:
        resp = await app.state.http_client.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=120.0)
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=f"Ollama error: {resp.text}")
        data = resp.json()
        text = data.get("response") or data.get("text") or ""
        if not text:
            text = "# Summary\n\n- Summarization returned empty output."
        return LlamaSummaryResponse(text=text)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"Failed to reach Ollama at {OLLAMA_URL}: {exc}")

# --- Main Execution --- 
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 