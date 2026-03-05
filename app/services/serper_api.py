import os
import requests
import json

class SerperService:
    def __init__(self):
        self.api_key = os.getenv("SERPER_API_KEY")
        self.base_url = "https://google.serper.dev/search"

    def find_trending_topics(self, niche: str, count: int = 5):
        """Scrapes Google News & Reddit for the latest buzz in a niche."""
        if not self.api_key:
            print("⚠️ SERPER_API_KEY missing.")
            return []

        # We look for "news" to get fresh topics
        payload = json.dumps({
            "q": f"latest trends in {niche} -site:youtube.com",
            "num": count,
            "tbs": "qdr:w"  # Query Date Range: Past Week
        })
        
        headers = {
            'X-API-KEY': self.api_key,
            'Content-Type': 'application/json'
        }

        try:
            response = requests.request("POST", self.base_url, headers=headers, data=payload)
            results = response.json()
            
            topics = []
            # Extract organic results
            for item in results.get("organic", []):
                topics.append(f"{item.get('title')}: {item.get('snippet')}")
            
            return topics
        except Exception as e:
            print(f"Error fetching trends: {e}")
            return []