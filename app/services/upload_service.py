import cloudinary
import cloudinary.uploader
import os
from dotenv import load_dotenv

load_dotenv()

class UploadService:
    def __init__(self):
        # Configure Cloudinary
        cloudinary.config(
            cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
            api_key=os.getenv("CLOUDINARY_API_KEY"),
            api_secret=os.getenv("CLOUDINARY_API_SECRET"),
            secure=True
        )

    def upload_pdf(self, file_path: str, filename: str) -> str:
        """
        Uploads a PDF file to Cloudinary and returns the secure URL.
        """
        print(f"☁️ Uploading {filename} to Cloudinary...")
        try:
            # Upload the file
            # resource_type="raw" is crucial for PDFs in Cloudinary
            response = cloudinary.uploader.upload(
                file_path, 
                resource_type="raw", 
                public_id=filename.replace(".pdf", ""),
                folder="scripts"
            )
            
            url = response.get("secure_url")
            print(f"✅ Upload Successful: {url}")
            return url
            
        except Exception as e:
            print(f"❌ Upload Failed: {e}")
            return None