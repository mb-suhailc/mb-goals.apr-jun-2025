import os
import json
import logging
import requests
import subprocess
from datetime import datetime

import azure.functions as func

# Azure Cognitive Services for Speech and Vision
from msrest.authentication import CognitiveServicesCredentials
import azure.cognitiveservices.speech as speechsdk
from azure.cognitiveservices.vision.computervision import ComputerVisionClient

# # Azure Blob Storage
from azure.storage.blob import BlobServiceClient
from azure.identity import DefaultAzureCredential

# # Azure OpenAI
from openai import AzureOpenAI


OPENAI_MODEL='o3-mini'
BLOB_ACCOUNT = "travelassistant"
BLOB_CONTAINER = "travel-assistant"

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

@app.route(route="travel_assistant")
def travel_assistant(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Travel assistant function received a request.")

    # Read request payload
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse("Invalid JSON input", status_code=400)
    
    # Validate allowed channels
    channel = body.get("channelId")
    if channel not in ("telegram", "webchat"):
        return func.HttpResponse(f"Unsupported channel: {channel}", status_code=400)
    
    # Get conversation ID from request (Bot Framework conversation id)
    conversation = body.get("conversation", {}).get("id")
    if not conversation:
        return func.HttpResponse("Missing conversation ID", status_code=400)
    
    # Determine user input type: text, audio, or image
    user_text = body.get("text")
    attachments = body.get("attachments", [])
    audio_transcript = None
    image_caption = None
    image_description = None

    # Input validation
    if not user_text and not attachments:
        return func.HttpResponse("No user input provided", status_code=400)
    if user_text and attachments:
        return func.HttpResponse("Cannot process both text and attachment together", status_code=400)
    
    if attachments:
        if len(attachments) > 1:
            return func.HttpResponse("Multiple attachments not supported", status_code=400)
        
        att = attachments[0]
        content_type = att.get("contentType", "")
        content_url = att.get("contentUrl")
        
        if content_type.startswith("audio"):
            if content_type in ("audio/ogg", "audio/wav"):
                try:
                    # Download audio content for transcription
                    res = requests.get(content_url)
                    if res.status_code != 200:
                        return func.HttpResponse("Failed to retrieve audio attachment", status_code=500)
                    audio_data = res.content

                    # If voice input is present, transcribe it
                    if audio_data:
                        # Write audio data to a temporary file
                        if content_type == "audio/ogg":
                            temp_audio_path = ogg_wav(audio_data)
                        else:
                            temp_audio_path = "/tmp/input_audio.wav"
                            with open(temp_audio_path, "wb") as f:
                                f.write(audio_data)
                        audio_config = speechsdk.AudioConfig(filename=temp_audio_path)

                        # Use Azure Speech SDK to transcribe audio
                        speech_key = os.getenv("SPEECH_KEY")
                        speech_region = os.getenv("SPEECH_REGION")
                        if not speech_key or not speech_region:
                            return func.HttpResponse("Speech service credentials not configured", status_code=500)
                        speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=speech_region)

                        recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
                        result = recognizer.recognize_once_async().get()
                        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
                            audio_transcript = result.text
                
                except Exception as e:
                    logging.error(f"Speech Service error: {e}")
            else:
                return func.HttpResponse(f"Unsupported audio type: {content_type}", status_code=400)

        elif content_type.startswith("image"):
            # Download image content for analysis
            res = requests.get(content_url)
            if res.status_code != 200:
                return func.HttpResponse("Failed to retrieve image attachment", status_code=500)
            image_data = res.content
            image_caption = att.get("name")

            # If image input is present, generate a description
            if image_data:
                # Use Azure Computer Vision to describe the image
                vision_key = os.getenv("CV_KEY")
                vision_endpoint = os.getenv("CV_ENDPOINT")
                if not vision_key or not vision_endpoint:
                    return func.HttpResponse("Vision service credentials not configured", status_code=500)
                cv_client = ComputerVisionClient(vision_endpoint, CognitiveServicesCredentials(vision_key))
                
                from io import BytesIO
                image_stream = BytesIO(image_data)
                try:
                    analysis = cv_client.describe_image_in_stream(image_stream)
                    if analysis.captions:
                        image_description = analysis.captions[0].text
                except Exception as e:
                    logging.error(f"Computer Vision API error: {e}")
        
        else:
            return func.HttpResponse(f"Unsupported attachment type: {content_type}", status_code=400)
        
    # Setup Blob storage client
    credential = DefaultAzureCredential()
    blob_service = BlobServiceClient(
        account_url=f"https://{BLOB_ACCOUNT}.blob.core.windows.net",
        credential=credential
    )
    container_client = blob_service.get_container_client(container=BLOB_CONTAINER)

    history_messages = []
    try:
        # List blobs prefixed by conversation ID and sort by creation time descending
        blobs = container_client.list_blobs(name_starts_with=conversation)
        sorted_blobs = sorted(blobs, key=lambda b: b.creation_time, reverse=True)
        for blob in sorted_blobs[:5]:
            blob_client = container_client.get_blob_client(blob.name)
            content = blob_client.download_blob().readall()
            history_messages.append(json.loads(content))
    except Exception as e:
        logging.error(f"Error retrieving conversation history: {e}")
    
    # Build conversation history text for prompt context
    history_text = ""
    for conv in reversed(history_messages):
        user_msg = conv.get("user", "")
        bot_msg = conv.get("assistant", "")
        history_text += f"\nUser: {user_msg}\nAssistant: {bot_msg}\n"
    
    user_contexts = []
    if history_text:
        user_contexts.append(f"### Conversation History:\n{history_text}\n")
    if audio_transcript:
        user_contexts.append(f"### Audio Transcript:\n{audio_transcript}\n")
    if image_description:
        user_contexts.append(f"### Image Description:\n{image_description}\n")
    if image_caption:
        user_contexts.append(f"### Image Caption:\n{image_caption}\n")
    if user_text:
        user_contexts.append(f"### User Query:\n{user_text}\n")

    user_prompt = '\n'.join(user_contexts)
    
    web_search_prompt = user_prompt + """  
\n\nAnalyze the provided user query and given context carefully.  
Your goal is to determine:
1. Whether performing a web search is needed.
2. If yes, generate a concise, effective search query suitable for a search engine like DuckDuckGo.

Output must be strictly a valid JSON object with exactly two keys:
- "search_required": a boolean (true or false).
- "search_query": a string (empty "" if search is not required).

Rules:
- Only say "search_required": true if the information clearly cannot be answered directly from the given context.
- "search_query" should be clean, short, and remove unnecessary words or filler.
- Never include extra text, explanation, or formatting outside the JSON.

Example Output:
{
  "search_required": true,
  "search_query": "best travel destinations in Europe in June"
}

or

{
  "search_required": false,
  "search_query": ""
}
"""

    client = AzureOpenAI(
        api_version=os.getenv("OPENAI_API_VERSION"),
        azure_endpoint=os.getenv("OPENAI_ENDPOINT"),
        api_key=os.getenv("OPENAI_KEY"),
    )
    
    web_search_consent = client.chat.completions.create(
        messages=[
            {"role": "system", "content": "You are a smart travel assistant."},
            {"role": "user", "content": web_search_prompt}
        ],
        max_completion_tokens=100000,
        model=OPENAI_MODEL
    )
    web_search_consent_json = json.loads(web_search_consent.choices[0].message.content)

    if web_search_consent_json.get("search_required") and web_search_consent_json.get("search_query"):
        search_results = google_search(web_search_consent_json.get("search_query"))
        if search_results:
            user_contexts.insert(-1, f"### Web Search Results:\n{search_results}\n")

    # Construct GPT prompt with system and user messages
    system_msg = {
        "role": "system",
        "content": "You’re a friendly travel assistant! Please help with travel-related questions only. "
        "If someone asks about something else, kindly respond with: "
        "'Oops! I can only help with travel questions. Feel free to ask about your next trip!' "
        "Keep your replies warm and brief."
    }

    # Request LLM to respond based on user content
    user_prompt = '\n'.join(user_contexts) + "\nRespond to the user's input appropriately."
    logging.info(f'LLM_PROMPT\n {user_prompt}')

    user_msg = {"role": "user", "content": user_prompt}

    query_response = client.chat.completions.create(
        messages=[system_msg, user_msg],
        max_completion_tokens=100000,
        model=OPENAI_MODEL
    )
    response_text = query_response.choices[0].message.content

    # Send the reply back on Telegram
    if channel == "telegram":
        telegram_token = os.getenv("TELEGRAM_TOKEN")
        requests.post(
            f"https://api.telegram.org/bot{telegram_token}/sendMessage", 
            json={
                "chat_id": conversation, 
                "text": response_text
            }
        )
    
    # Save the new conversation exchange to Blob Storage
    try:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        blob_name = f"{conversation}/{timestamp}.json"
        blob_client = container_client.get_blob_client(blob_name)
        
        conv_record = json.dumps({
            "user": '\n'.join(user_contexts[1:] if history_text else user_contexts), 
            "assistant": response_text
        })
        blob_client.upload_blob(conv_record, overwrite=True)
    except Exception as e:
        logging.error(f"Failed to save conversation history: {e}")
    
    return func.HttpResponse(body=json.dumps({"type": "message", "text": response_text}), 
                             status_code=200,
                             mimetype="application/json")
    

def ogg_wav(ogg_data: bytes) -> str:
    """OGG to WAV Conversion"""
    # Write OGG to temp file
    ogg_path = "/tmp/input_audio.ogg"
    with open(ogg_path, "wb") as f:
        f.write(ogg_data)

    # Paths for FFmpeg and output
    ffmpeg_path = "./ffmpeg"
    wav_path = "/tmp/input_audio.wav"

    # Ensure FFmpeg is executable and ignore if it already is
    try:
        os.chmod(ffmpeg_path, 0o755)
    except Exception:
        pass  

    # Run FFmpeg conversion
    subprocess.run([ffmpeg_path, "-y", "-i", ogg_path, wav_path], check=True)

    return wav_path


def google_search(query: str):
    """Performs a Google search using SerpAPI and returns relevant text snippets."""
    serp_api_key = os.getenv("SERP_API_KEY")
    if not serp_api_key:
        logging.error("SerpAPI credentials not configured")
        return

    url = "https://serpapi.com/search"
    params = {
        "q": query,
        "api_key": serp_api_key,
        "engine": "google",
        "num": 5
    }

    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()

    results = ""
    # Parse organic search results
    for idx, result in enumerate(data.get("organic_results", []), 1):
        title = result.get("title", "")
        snippet = result.get("snippet", "")
        link = result.get("link", "")
        results += f"{idx}. {title}\n{snippet}\n{link}\n\n"

    return results
