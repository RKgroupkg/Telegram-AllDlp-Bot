import requests
import asyncio
import os
from mutagen.flac import FLAC
from mutagen.flac import Picture
from random import randrange

from src.logging import LOGGER

logger = LOGGER(__name__)


def get_random_user_agent():
    """Generate a random user agent string for requests."""
    return (
        f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_{randrange(11, 15)}_{randrange(4, 9)}) "
        f"AppleWebKit/{randrange(530, 537)}.{randrange(30, 37)} (KHTML, like Gecko) "
        f"Chrome/{randrange(80, 105)}.0.{randrange(3000, 4500)}.{randrange(60, 125)} "
        f"Safari/{randrange(530, 537)}.{randrange(30, 36)}"
    )


class DeezerDownloader:
    """Handler for downloading and tagging music from Deezer."""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': get_random_user_agent()
        })
        self.progress_callback = None
        logger.debug("DeezerDownloader initialized")
    
    def set_progress_callback(self, callback):
        """Set a callback function for download progress updates."""
        self.progress_callback = callback
        logger.debug("Progress callback set")
    
    def get_track_by_isrc(self, isrc):
        """
        Fetch track information from Deezer API using ISRC.
        
        Args:
            isrc: International Standard Recording Code
            
        Returns:
            dict: Track data or None if failed
        """
        try:
            url = f"https://api.deezer.com/2.0/track/isrc:{isrc}"
            logger.debug(f"Fetching track data from: {url}")
            response = self.session.get(url)
            response.raise_for_status()
            
            data = response.json()
            
            if 'error' in data:
                logger.error(f"Deezer API error: {data['error']['message']}")
                return None
            
            logger.debug(f"Successfully retrieved track data for ISRC: {isrc}")
            return data
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed while fetching track data: {e}")
            return None
    
    def extract_metadata(self, track_data):
        """
        Extract relevant metadata from Deezer track data.
        
        Args:
            track_data: Raw track data from Deezer API
            
        Returns:
            dict: Extracted metadata
        """
        metadata = {
            'title': track_data.get('title', ''),
            'title_short': track_data.get('title_short', ''),
            'duration': track_data.get('duration', 0),
            'track_position': track_data.get('track_position', 1),
            'disk_number': track_data.get('disk_number', 1),
            'isrc': track_data.get('isrc', ''),
            'release_date': track_data.get('release_date', ''),
            'explicit_lyrics': track_data.get('explicit_lyrics', False),
            'deezer_link': track_data.get('link', ''),
            'preview_url': track_data.get('preview', '')
        }
        
        # Extract artist information
        if 'artist' in track_data:
            metadata['artist'] = track_data['artist'].get('name', '')
            metadata['artist_id'] = track_data['artist'].get('id', '')
        
        # Extract contributors (main artists)
        if 'contributors' in track_data:
            artists = [
                contributor.get('name', '')
                for contributor in track_data['contributors']
                if contributor.get('role') == 'Main'
            ]
            metadata['artists'] = ', '.join(artists) if artists else metadata.get('artist', '')
        
        # Extract album information
        if 'album' in track_data:
            album = track_data['album']
            metadata['album'] = album.get('title', '')
            metadata['album_id'] = album.get('id', '')
            metadata['cover_url'] = album.get('cover_xl', album.get('cover_big', ''))
            metadata['cover_md5'] = album.get('md5_image', '')
        
        logger.debug(f"Extracted metadata for: {metadata.get('artists', 'Unknown')} - {metadata.get('title', 'Unknown')}")
        return metadata
    
    def download_cover_art(self, cover_url, filename):
        """
        Download cover art from URL.
        
        Args:
            cover_url: URL of the cover art
            filename: Base filename for saving
            
        Returns:
            str: Path to downloaded cover or None if failed
        """
        if not cover_url:
            logger.debug("No cover URL provided")
            return None
        
        try:
            logger.debug(f"Downloading cover art from: {cover_url}")
            response = self.session.get(cover_url)
            response.raise_for_status()
            
            cover_path = f"{filename}_cover.jpg"
            with open(cover_path, 'wb') as f:
                f.write(response.content)
            
            logger.info(f"Cover art downloaded: {cover_path}")
            return cover_path
        except Exception as e:
            logger.error(f"Failed to download cover art: {e}")
            return None
    
    def embed_metadata(self, file_path, metadata, cover_path=None):
        """
        Embed metadata and cover art into FLAC file.
        
        Args:
            file_path: Path to the FLAC file
            metadata: Dictionary containing metadata
            cover_path: Optional path to cover art file
        """
        try:
            logger.debug(f"Embedding metadata into: {file_path}")
            audio = FLAC(file_path)
            audio.clear()
            
            # Map metadata to FLAC tags
            tag_mapping = {
                'title': 'TITLE',
                'album': 'ALBUM',
                'release_date': 'DATE',
                'isrc': 'ISRC'
            }
            
            for meta_key, tag_key in tag_mapping.items():
                if metadata.get(meta_key):
                    audio[tag_key] = metadata[meta_key]
            
            # Handle artist(s)
            if metadata.get('artists'):
                audio['ARTIST'] = metadata['artists']
            elif metadata.get('artist'):
                audio['ARTIST'] = metadata['artist']
            
            # Handle numeric fields
            if metadata.get('track_position'):
                audio['TRACKNUMBER'] = str(metadata['track_position'])
            if metadata.get('disk_number'):
                audio['DISCNUMBER'] = str(metadata['disk_number'])
            
            # Embed cover art
            if cover_path and os.path.exists(cover_path):
                logger.debug(f"Embedding cover art from: {cover_path}")
                with open(cover_path, 'rb') as f:
                    cover_data = f.read()
                
                picture = Picture()
                picture.type = 3  # Cover (front)
                picture.mime = 'image/jpeg'
                picture.desc = 'Cover'
                picture.data = cover_data
                audio.add_picture(picture)
            
            audio.save()
            logger.info(f"Metadata embedded successfully in: {file_path}")
            
        except Exception as e:
            logger.error(f"Failed to embed metadata: {e}", exc_info=True)
    
    def _sanitize_filename(self, text):
        """
        Sanitize text for use in filenames.
        
        Args:
            text: Text to sanitize
            
        Returns:
            str: Sanitized filename-safe text
        """
        return "".join(
            c for c in text if c.isalnum() or c in (' ', '-', '_')
        ).rstrip()
    
    async def download_by_isrc(self, isrc, output_dir="."):
        """
        Download track by ISRC code.
        
        Args:
            isrc: International Standard Recording Code
            output_dir: Directory to save the downloaded file
            
        Returns:
            bool: True if successful, False otherwise
        """
        logger.info(f"Starting download for ISRC: {isrc}")
        
        # Fetch track data
        track_data = self.get_track_by_isrc(isrc)
        if not track_data:
            logger.error("Failed to retrieve track data from Deezer API")
            return False
        
        metadata = self.extract_metadata(track_data)
        logger.info(
            f"Found track: {metadata.get('artists', 'Unknown')} - "
            f"{metadata.get('title', 'Unknown')}"
        )
        
        # Get track ID
        track_id = track_data.get('id')
        if not track_id:
            logger.error("No track ID found in Deezer API response")
            return False
        
        logger.debug(f"Track ID: {track_id}")
        
        # Request download URL from API
        api_url = f"https://api.deezmate.com/dl/{track_id}"
        logger.debug(f"Requesting download URL from: {api_url}")
        
        try:
            response = self.session.get(api_url)
            response.raise_for_status()
            api_data = response.json()
            
            if not api_data.get('success'):
                logger.error("Download API request failed")
                return False
            
            links = api_data.get('links', {})
            flac_url = links.get('flac')
            
            if not flac_url:
                logger.error("No FLAC download link in API response")
                return False
            
            logger.info("Successfully obtained FLAC download URL")
            
        except Exception as e:
            logger.error(f"Failed to get download URL from API: {e}", exc_info=True)
            return False
        
        # Download FLAC file
        logger.info("Downloading FLAC file...")
        try:
            response = self.session.get(flac_url, stream=True)
            response.raise_for_status()
            
            # Prepare filename
            safe_title = self._sanitize_filename(metadata.get('title', 'Unknown'))
            safe_artist = self._sanitize_filename(metadata.get('artists', 'Unknown'))
            filename = f"{safe_artist} - {safe_title}.flac"
            file_path = os.path.join(output_dir, filename)
            
            # Ensure output directory exists
            os.makedirs(output_dir, exist_ok=True)
            
            # Write file
            with open(file_path, 'wb') as f:
                f.write(response.content)
            
            file_size = len(response.content)
            logger.info(
                f"Downloaded {file_size} bytes ({file_size / (1024*1024):.2f} MB) to: {file_path}"
            )
            
            if self.progress_callback:
                self.progress_callback(file_size, file_size)
            
            # Download cover art
            cover_path = None
            if metadata.get('cover_url'):
                logger.info("Downloading cover art...")
                base_filename = os.path.join(output_dir, f"{safe_artist} - {safe_title}")
                cover_path = self.download_cover_art(metadata['cover_url'], base_filename)
            
            # Embed metadata
            logger.info("Embedding metadata...")
            self.embed_metadata(file_path, metadata, cover_path)
            
            # Clean up cover art file
            if cover_path and os.path.exists(cover_path):
                os.remove(cover_path)
                logger.debug(f"Removed temporary cover file: {cover_path}")
            
            logger.info(f"Successfully downloaded and tagged: {filename}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to download file: {e}", exc_info=True)
            return False


async def main():
    """Main function for testing the downloader."""
    logger.info("=== DeezerDL - Deezer Downloader ===")
    downloader = DeezerDownloader()
    
    isrc = "USUM71027402"
    output_dir = "tmp"
    
    success = await downloader.download_by_isrc(isrc, output_dir)
    if success:
        logger.info("Download completed successfully!")
    else:
        logger.error("Download failed!")


if __name__ == "__main__":
    try:
        import sys
        if sys.platform == "win32":
            import os
            os.system("chcp 65001 > nul")
            try:
                sys.stdout.reconfigure(encoding='utf-8')
            except Exception:
                pass
    except Exception:
        pass
        
    asyncio.run(main())