#!/bin/bash

# Vexa Bot Interaction Script

# --- Configuration ---
# Default Vexa API base URL and Admin API URL will be constructed using ports from .env
# Default ports if not found in .env
DEFAULT_API_GATEWAY_HOST_PORT="8056"
DEFAULT_ADMIN_API_HOST_PORT="8057"

API_GATEWAY_HOST_PORT=""
ADMIN_API_HOST_PORT=""

# --- Helper Functions ---
echo_error() {
    echo -e "\033[0;31mERROR: $1\033[0m" >&2
}

echo_info() {
    echo -e "\033[0;32mINFO: $1\033[0m"
}

echo_warn() {
    echo -e "\033[0;33mWARN: $1\033[0m"
}

# --- Check for dependencies ---
if ! command -v curl &> /dev/null; then
    echo_error "curl is not installed. Please install it to run this script."
    exit 1
fi

if ! command -v jq &> /dev/null; then
    echo_warn "jq is not installed. JSON parsing will be basic and less robust."
    echo_warn "It is highly recommended to install jq: sudo apt-get install jq (or similar for your OS)"
    JQ_INSTALLED=false
else
    JQ_INSTALLED=true
fi

# --- Read .env file for ADMIN_API_TOKEN and HOST PORTS ---
ADMIN_TOKEN=""
if [ -f ".env" ]; then
    echo_info "Reading configuration from .env file..."
    # Source .env file if it exists and extract ADMIN_API_TOKEN
    ADMIN_TOKEN_FROM_ENV=$(grep -E '^[[:space:]]*ADMIN_API_TOKEN=' .env | head -n 1 | cut -d '=' -f2-)
    if [[ -n "$ADMIN_TOKEN_FROM_ENV" ]]; then
        ADMIN_TOKEN=$(echo "$ADMIN_TOKEN_FROM_ENV" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")
        if [[ -n "$ADMIN_TOKEN" ]]; then
            echo_info "Using Admin API Token from .env file."
        else
            echo_warn "Found ADMIN_API_TOKEN in .env but it appears to be empty after parsing."
        fi
    else
        echo_warn "ADMIN_API_TOKEN not found in .env file or line is malformed."
    fi

    # Extract API_GATEWAY_HOST_PORT
    TEMP_API_PORT=$(grep -E '^[[:space:]]*API_GATEWAY_HOST_PORT=' .env | head -n 1 | cut -d '=' -f2- | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")
    if [[ -n "$TEMP_API_PORT" ]]; then
        API_GATEWAY_HOST_PORT=$TEMP_API_PORT
        echo_info "Using API_GATEWAY_HOST_PORT from .env: $API_GATEWAY_HOST_PORT"
    else
        echo_warn "API_GATEWAY_HOST_PORT not found in .env or empty."
    fi

    # Extract ADMIN_API_HOST_PORT
    TEMP_ADMIN_PORT=$(grep -E '^[[:space:]]*ADMIN_API_HOST_PORT=' .env | head -n 1 | cut -d '=' -f2- | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")
    if [[ -n "$TEMP_ADMIN_PORT" ]]; then
        ADMIN_API_HOST_PORT=$TEMP_ADMIN_PORT
        echo_info "Using ADMIN_API_HOST_PORT from .env: $ADMIN_API_HOST_PORT"
    else
        echo_warn "ADMIN_API_HOST_PORT not found in .env or empty."
    fi
else
    echo_warn ".env file not found. Will prompt for Admin Token and use default ports."
fi

# Set defaults if still empty
if [[ -z "$API_GATEWAY_HOST_PORT" ]]; then
    echo_warn "API_GATEWAY_HOST_PORT not set, using default: $DEFAULT_API_GATEWAY_HOST_PORT"
    API_GATEWAY_HOST_PORT=$DEFAULT_API_GATEWAY_HOST_PORT
fi
if [[ -z "$ADMIN_API_HOST_PORT" ]]; then
    echo_warn "ADMIN_API_HOST_PORT not set, using default: $DEFAULT_ADMIN_API_HOST_PORT"
    ADMIN_API_HOST_PORT=$DEFAULT_ADMIN_API_HOST_PORT
fi

# Construct Base URLs
BASE_URL="http://localhost:$API_GATEWAY_HOST_PORT"
ADMIN_API_URL="http://localhost:$ADMIN_API_HOST_PORT"
echo_info "Effective BASE_URL: $BASE_URL"
echo_info "Effective ADMIN_API_URL: $ADMIN_API_URL"

# --- Variables for New User and Bot ---
USER_EMAIL="testuser$(date +%s)@example.com"
USER_NAME="Test User $(date +%s)"
BOT_NAME="VexaFirstTestBot"
PLATFORM="google_meet"

# --- Function to stop the bot --- 
MEETING_ID_TO_STOP=""
USER_API_KEY_FOR_STOP=""

function stop_the_bot() {
    if [[ -n "$MEETING_ID_TO_STOP" && -n "$USER_API_KEY_FOR_STOP" ]]; then
        echo_info "\nAttempting to stop the bot for meeting $MEETING_ID_TO_STOP..."
        STOP_RESPONSE=$(curl -s -X DELETE \
            -H "Content-Type: application/json" \
            -H "X-API-Key: $USER_API_KEY_FOR_STOP" \
            "$BASE_URL/bots/$PLATFORM/$MEETING_ID_TO_STOP")
        
        if [[ "$JQ_INSTALLED" == true ]]; then
            STOP_MESSAGE=$(echo "$STOP_RESPONSE" | jq -r .message)
            echo_info "Stop bot response: $STOP_MESSAGE"
        else
            echo_info "Stop bot raw response: $STOP_RESPONSE"
        fi
    else
        echo_warn "Could not stop bot: Meeting ID or User API Key for stopping not set."
    fi
    echo_info "Exiting script."
    exit 0
}

# Trap SIGINT (Ctrl+C) and call stop_the_bot
trap stop_the_bot SIGINT SIGTERM

# --- 1. Create User ---
echo_info "Creating a new user: $USER_NAME ($USER_EMAIL)"
CREATE_USER_PAYLOAD=$(cat <<-END
{
  "email": "$USER_EMAIL",
  "name": "$USER_NAME",
  "max_concurrent_bots": 2
}
END
)

# Use ADMIN_API_URL for admin actions
CREATE_USER_RESPONSE=$(curl -s -X POST \
    -H "Content-Type: application/json" \
    -H "X-Admin-API-Key: $ADMIN_TOKEN" \
    -d "$CREATE_USER_PAYLOAD" \
    "$ADMIN_API_URL/admin/users")

if [[ "$JQ_INSTALLED" == true ]]; then
    USER_ID=$(echo "$CREATE_USER_RESPONSE" | jq -r .id)
    USER_EMAIL_RES=$(echo "$CREATE_USER_RESPONSE" | jq -r .email)
    if [[ "$USER_ID" == "null" || -z "$USER_ID" ]]; then
        echo_error "Failed to create user. Response: $CREATE_USER_RESPONSE"
        exit 1
    fi
    echo_info "User created successfully. ID: $USER_ID, Email: $USER_EMAIL_RES"
else
    echo_info "Create user raw response: $CREATE_USER_RESPONSE"
    # Basic parsing if jq is not available (less reliable)
    USER_ID=$(echo "$CREATE_USER_RESPONSE" | grep -o '"id":[0-9]*' | grep -o '[0-9]*')
    if [[ -z "$USER_ID" ]]; then
        echo_error "Failed to parse User ID from response. Ensure user was created via Admin Panel or install jq."
        exit 1
    fi
    echo_info "User likely created. Parsed ID: $USER_ID (Install jq for better parsing)"
fi

# --- 2. Create Token for User ---
echo_info "Creating API token for user ID: $USER_ID"
# According to vexa_client.py, this endpoint does not take a JSON payload.
# It's a POST request to /admin/users/{user_id}/tokens

# Use ADMIN_API_URL for admin actions
CREATE_TOKEN_RESPONSE=$(curl -s -X POST \
    -H "X-Admin-API-Key: $ADMIN_TOKEN" \
    "$ADMIN_API_URL/admin/users/$USER_ID/tokens")

if [[ "$JQ_INSTALLED" == true ]]; then
    USER_API_KEY=$(echo "$CREATE_TOKEN_RESPONSE" | jq -r .token)
    USER_API_KEY_FOR_STOP="$USER_API_KEY" # Set for trap
    if [[ "$USER_API_KEY" == "null" || -z "$USER_API_KEY" ]]; then
        echo_error "Failed to create token. Response: $CREATE_TOKEN_RESPONSE"
        exit 1
    fi
    echo_info "API Token created successfully: $USER_API_KEY"
else
    echo_info "Create token raw response: $CREATE_TOKEN_RESPONSE"
    # Basic parsing if jq is not available (less reliable)
    # Attempt to find a field named 'token' or 'api_key' as a fallback for non-jq users.
    # Prefer 'token' if both somehow existed, but focus on the more likely one based on recent findings.
    USER_API_KEY=$(echo "$CREATE_TOKEN_RESPONSE" | grep -o '"token":"[^"]*"' | grep -o ':"[^"]*"' | sed 's/:"//;s/"$//')
    if [[ -z "$USER_API_KEY" ]]; then # Fallback if 'token' field wasn't found, try 'api_key'
        USER_API_KEY=$(echo "$CREATE_TOKEN_RESPONSE" | grep -o '"api_key":"[^"]*"' | grep -o ':"[^"]*"' | sed 's/:"//;s/"$//')
    fi
    USER_API_KEY_FOR_STOP="$USER_API_KEY"
    if [[ -z "$USER_API_KEY" ]]; then
        echo_error "Failed to parse API Key from response. Ensure token was created or install jq."
        exit 1
    fi
    echo_info "API Token likely created. Parsed Key: $USER_API_KEY (Install jq for better parsing)"
fi

# --- 3. Request Google Meet ID ---
while true; do
    read -p "Enter the Google Meet ID (e.g., abc-defg-hij): " GOOGLE_MEET_ID
    # Basic validation for meet ID format (3 letters - 4 letters - 3 letters)
    if [[ "$GOOGLE_MEET_ID" =~ ^[a-zA-Z]{3}-[a-zA-Z]{4}-[a-zA-Z]{3}$ ]]; then
        MEETING_ID_TO_STOP="$GOOGLE_MEET_ID" # Set for trap
        break
    else
        echo_warn "Invalid Google Meet ID format. Please use 'xxx-yyyy-zzz' (e.g., abc-defg-hij)."
    fi
done

# --- 4. Send Bot to Meeting ---
echo_info "Requesting bot '$BOT_NAME' for Google Meet ID: $GOOGLE_MEET_ID"
REQUEST_BOT_PAYLOAD=$(cat <<-END
{
  "platform": "$PLATFORM",
  "native_meeting_id": "$GOOGLE_MEET_ID",
  "bot_name": "$BOT_NAME"
}
END
)

# Use BASE_URL for user actions
REQUEST_BOT_RESPONSE=$(curl -s -X POST \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $USER_API_KEY" \
    -d "$REQUEST_BOT_PAYLOAD" \
    "$BASE_URL/bots")

MEETING_UUID=""
if [[ "$JQ_INSTALLED" == true ]]; then
    BOT_REQUEST_MSG=$(echo "$REQUEST_BOT_RESPONSE" | jq -r .message)
    MEETING_UUID=$(echo "$REQUEST_BOT_RESPONSE" | jq -r .meeting_uuid) # Assuming the response contains meeting_uuid or similar
    echo_info "Bot request response: $BOT_REQUEST_MSG"
    if [[ "$MEETING_UUID" == "null" || -z "$MEETING_UUID" ]]; then
       echo_warn "Could not get a meeting_uuid from bot request response. Transcript polling might rely on platform/native_meeting_id only."
       echo_warn "Bot request raw response: $REQUEST_BOT_RESPONSE"
    else
        echo_info "Meeting UUID: $MEETING_UUID"
    fi
else
    echo_info "Bot request raw response: $REQUEST_BOT_RESPONSE"
    # Attempt basic parse for meeting_uuid if needed by transcript endpoint, though client uses platform/native_id
fi

# Check if the bot request was successful enough to proceed (e.g. status code was 2xx)
# Curl with -s silences output but not errors. A more robust check would be on HTTP status code, but this is a simple script.
# We'll assume if USER_API_KEY is set and GOOGLE_MEET_ID is set, the request was likely sent.

# --- Wait for bot admission and provide user instructions ---
echo_info "Bot '$BOT_NAME' has been requested for Google Meet ID: $GOOGLE_MEET_ID"
echo_warn "Please admit the bot into your Google Meet session now."
echo_warn "Polling for transcripts will begin shortly."

COUNTDOWN_SECONDS=10
echo_info "Starting transcript polling in:"
for i in $(seq $COUNTDOWN_SECONDS -1 1); do
    echo -ne "$i... "
    sleep 1
done
echo "GO!"

# --- 5. Poll for Transcripts --- 
echo_info "Starting to poll for transcripts for $PLATFORM/$GOOGLE_MEET_ID... Press Ctrl+C to stop."
LAST_TRANSCRIPT_COUNT=0

while true; do
    # Use BASE_URL for user actions
    # Corrected endpoint to match vexa_client.py: /transcripts/{platform}/{native_meeting_id}
    GET_TRANSCRIPT_RESPONSE=$(curl -s -X GET \
        -H "Content-Type: application/json" \
        -H "X-API-Key: $USER_API_KEY" \
        "$BASE_URL/transcripts/$PLATFORM/$GOOGLE_MEET_ID")

    if [[ "$JQ_INSTALLED" == true ]]; then
        CURRENT_TRANSCRIPTS=$(echo "$GET_TRANSCRIPT_RESPONSE" | jq -r '.segments // []')

        NEW_SEGMENT_COUNT=$(echo "$CURRENT_TRANSCRIPTS" | jq 'length // 0')

        if [[ "$NEW_SEGMENT_COUNT" -gt "$LAST_TRANSCRIPT_COUNT" ]]; then
            echo_info "--- New Transcript Segments ($PLATFORM/$GOOGLE_MEET_ID) ---"
            jq -r --argjson last_count "$LAST_TRANSCRIPT_COUNT" '.[$last_count:] | .[] | ("Speaker " + (.speaker // "unknown") + ": " + .text)' <<< "$CURRENT_TRANSCRIPTS"
            LAST_TRANSCRIPT_COUNT=$NEW_SEGMENT_COUNT
            echo "---------------------------------------"
        elif [[ "$GET_TRANSCRIPT_RESPONSE" == *"not found"* || "$GET_TRANSCRIPT_RESPONSE" == *"NotFoundError"* ]]; then
            echo_warn "Meeting or transcript not found for $PLATFORM/$GOOGLE_MEET_ID. Bot may have stopped or not started properly."
            # Consider breaking loop or specific error handling here
        fi
    else
        # Basic output if jq is not available
        echo "Raw transcript response ($PLATFORM/$GOOGLE_MEET_ID): $GET_TRANSCRIPT_RESPONSE"
    fi
    
    sleep 5 # Poll every 5 seconds
done 