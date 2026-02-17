from imports import *
from main.utils.util import log

class GeminiClient:
    def __init__(self, apiKey: str):
        self.apiKey = apiKey

    def generateContent(self, prompt: str, systemInstruction: Optional[str] = None, model: str = "gemini-2.5-flash-lite") -> Optional[str]:
        baseUrl = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        url = f"{baseUrl}?key={self.apiKey}"
        
        combinedPrompt = f"INSTRUCTION: {systemInstruction}\n\nQUERY: {prompt}" if systemInstruction else prompt

        payload = {
            "contents": [{
                "role": "user",
                "parts": [{"text": combinedPrompt}]
            }],
            "tools": [
                {
                    "google_search": {} 
                }
            ],

            "systemInstruction": {
                "parts": [{"text": systemInstruction}]
            } if systemInstruction else None
        }

        retries = 5
        for i in range(retries):
            try:
                response = requests.post(url, json=payload, timeout=30)
                
                if response.status_code == 200:
                    result = response.json()
                    return result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text')
                
                if response.status_code in [429, 500, 502, 503, 504]:
                    waitTime = 2 ** i
                    time.sleep(waitTime)
                    continue
                else:
                    log("gemini", f"Error {response.status_code}: {response.text}")
                    break
                    
            except requests.exceptions.RequestException as e:
                waitTime = 2 ** i
                time.sleep(waitTime)

        log("gemini", "Maximum retries reached. Could not complete the request.")
        return None