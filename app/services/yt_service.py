import os
from googleapiclient.discovery import build
from datetime import datetime, timedelta

class YouTubeService:
    def __init__(self):
        # We will add this key to your .env file in a moment
        api_key = os.getenv("YOUTUBE_API_KEY")
        if not api_key:
            print("⚠️ WARNING: YOUTUBE_API_KEY not found in .env")
            self.youtube = None
        else:
            self.youtube = build('youtube', 'v3', developerKey=api_key)

    def search_videos(self, query: str, max_results: int = 5):
        """Finds recent videos for a specific niche/topic."""
        if not self.youtube:
            return []
            
        # Search for videos published in the last 30 days
        published_after = (datetime.utcnow() - timedelta(days=30)).isoformat() + "Z"
        
        request = self.youtube.search().list(
            part="snippet",
            q=query,
            type="video",
            order="viewCount",  # Get the most popular ones first
            publishedAfter=published_after,
            maxResults=max_results
        )
        response = request.execute()
        
        videos = []
        for item in response.get("items", []):
            video_id = item["id"]["videoId"]
            title = item["snippet"]["title"]
            videos.append({"id": video_id, "title": title})
            
        return videos

    def get_video_stats(self, video_id: str):
        """Fetches view count and publish date to calculate velocity."""
        if not self.youtube:
            return None
            
        request = self.youtube.videos().list(
            part="statistics,snippet",
            id=video_id
        )
        response = request.execute()
        
        if not response["items"]:
            return None
            
        item = response["items"][0]
        stats = item["statistics"]
        snippet = item["snippet"]
        
        return {
            "view_count": int(stats.get("viewCount", 0)),
            "like_count": int(stats.get("likeCount", 0)),
            "comment_count": int(stats.get("commentCount", 0)),
            "published_at": snippet["publishedAt"],
            "channel_title": snippet["channelTitle"]
        }