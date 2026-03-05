from youtube_transcript_api import YouTubeTranscriptApi
import re

class ScriptFetcher:
    def get_video_id(self, url: str):
        """Extract YouTube video ID from URL"""
        patterns = [
            r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
            r'(?:embed\/)([0-9A-Za-z_-]{11})',
            r'(?:shorts\/)([0-9A-Za-z_-]{11})',
            r'^([0-9A-Za-z_-]{11})$'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def fetch_transcript(self, video_url: str):
        """
        Fetches transcript using object-access (.text) instead of dict-access (['text']).
        """
        video_id = self.get_video_id(video_url)
        if not video_id:
            print(f"❌ Invalid YouTube URL: {video_url}")
            return None

        print(f"🔄 Fetching transcript for: {video_id}")

        try:
            # 1. Get the list of transcripts
            # (We use the static method if instance method fails, covering all bases)
            try:
                transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            except AttributeError:
                api = YouTubeTranscriptApi()
                transcript_list = api.list(video_id)

            # 2. Find English
            try:
                transcript = transcript_list.find_transcript(['en', 'en-US', 'en-GB'])
                print(f"✅ Detected Manual English: {transcript.language}")
            except:
                try:
                    transcript = transcript_list.find_generated_transcript(['en', 'en-US', 'en-GB'])
                    print(f"⚠️ Using auto-generated English: {transcript.language}")
                except:
                     print("❌ No English transcript found.")
                     return None
            
            # 3. Fetch the data
            transcript_data = transcript.fetch()
            
            # --- THE FIX IS HERE ---
            # We check if it's a Dict or an Object to be 100% safe
            full_text = ""
            if transcript_data and isinstance(transcript_data[0], dict):
                # It is a Dictionary (Standard)
                full_text = " ".join([entry['text'] for entry in transcript_data])
            else:
                # It is an Object (Your Version)
                full_text = " ".join([entry.text for entry in transcript_data])
            # -----------------------

            return full_text
            
        except Exception as e:
            print(f"❌ Error in ScriptFetcher: {e}")
            return None