import os
import re
import time
import base64
import requests
import json
from mutagen.flac import FLAC, Picture
from mutagen.id3 import PictureType

from src.logging import LOGGER

logger = LOGGER(__name__)


class ProgressCallback:
    """Default progress callback for download operations."""
    
    def __call__(self, current, total):
        """
        Display download progress.
        
        Args:
            current: Current downloaded bytes
            total: Total bytes to download
        """
        if total > 0:
            percent = (current / total) * 100
            logger.debug(f"Progress: {percent:.2f}% ({current}/{total})")
        else:
            logger.debug(f"Downloaded: {current / (1024 * 1024):.2f} MB")


class TidalDownloader:
    """Handler for downloading and tagging music from Tidal."""
    
    def __init__(self, timeout=30, max_retries=3, api_url=None):
        """
        Initialize Tidal downloader.
        
        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum number of download retry attempts
            api_url: Custom API URL (optional)
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.download_chunk_size = 256 * 1024
        self.progress_callback = ProgressCallback()
        self.client_id = base64.b64decode("NkJEU1JkcEs5aHFFQlRnVQ==").decode()
        self.client_secret = base64.b64decode(
            "eGV1UG1ZN25icFo5SUliTEFjUTkzc2hrYTFWTmhlVUFxTjZJY3N6alRHOD0="
        ).decode()
        self.api_url = api_url or "https://hifi.401658.xyz"
        logger.debug(f"TidalDownloader initialized with API: {self.api_url}")
    
    @staticmethod
    def get_available_apis():
        """
        Fetch list of available API instances from status endpoint.
        
        Returns:
            list: Available API instances sorted by response time
        """
        try:
            logger.debug("Fetching available API instances...")
            response = requests.get(
                "https://status.monochrome.tf/api/stream", 
                timeout=10, 
                stream=True
            )
            
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        data = json.loads(line_str[6:])
                        
                        api_instances = [
                            inst for inst in data.get('instances', [])
                            if inst.get('instance_type') == 'api' 
                            and inst.get('last_check', {}).get('success')
                        ]
                        
                        api_instances.sort(key=lambda x: x.get('avg_response_time', 9999))
                        
                        logger.info(f"Found {len(api_instances)} available API instances")
                        return api_instances
                        
        except Exception as e:
            logger.error(f"Failed to fetch API list: {e}")
            return []
    
    @staticmethod
    def select_api_interactive():
        """
        Display available APIs and let user select one interactively.
        
        Returns:
            str: Selected API URL
        """
        apis = TidalDownloader.get_available_apis()
        
        if not apis:
            logger.warning("No APIs available, using default: https://hifi.401658.xyz")
            return "https://hifi.401658.xyz"
        
        logger.info("\n=== Available API Instances ===")
        logger.info(f"{'No':<4} {'URL':<40} {'Status':<8} {'Uptime':<8} {'Avg Response':<12}")
        logger.info("-" * 80)
        
        for i, api in enumerate(apis, 1):
            url = api.get('url', 'N/A')
            status = "UP" if api.get('last_check', {}).get('success') else "DOWN"
            uptime = f"{api.get('uptime', 0):.1f}%"
            avg_time = f"{api.get('avg_response_time', 0)}ms"
            
            logger.info(f"{i:<4} {url:<40} {status:<8} {uptime:<8} {avg_time:<12}")
        
        logger.info("\n0    Use default (https://hifi.401658.xyz)")
        logger.info("-" * 80)
        
        while True:
            try:
                choice = input(f"\nSelect API (0-{len(apis)}) [1 for fastest]: ").strip()
                
                if not choice:
                    choice = "1"
                
                choice_num = int(choice)
                
                if choice_num == 0:
                    logger.info("Using default API")
                    return "https://hifi.401658.xyz"
                elif 1 <= choice_num <= len(apis):
                    selected_url = apis[choice_num - 1]['url']
                    logger.info(f"Selected API: {selected_url}")
                    return selected_url
                else:
                    logger.warning(f"Invalid choice. Please enter 0-{len(apis)}")
            except ValueError:
                logger.warning("Invalid input. Please enter a number.")
            except KeyboardInterrupt:
                logger.info("\nUsing default API")
                return "https://hifi.401658.xyz"

    def set_progress_callback(self, callback):
        """
        Set a custom progress callback function.
        
        Args:
            callback: Function to call with (current, total) progress
        """
        self.progress_callback = callback
        logger.debug("Custom progress callback set")

    def sanitize_filename(self, filename):
        """
        Sanitize filename by removing invalid characters.
        
        Args:
            filename: Raw filename string
            
        Returns:
            str: Sanitized filename safe for file systems
        """
        if not filename: 
            return "Unknown Track"
        
        sanitized = re.sub(r'[\\/*?:"<>|]', "", str(filename))
        sanitized = re.sub(r'\s+', ' ', sanitized).strip()
        
        return sanitized or "Unnamed Track"

    def get_access_token(self):
        """
        Obtain OAuth access token from Tidal.
        
        Returns:
            str: Access token or None if failed
        """
        refresh_url = "https://auth.tidal.com/v1/oauth2/token"
        
        payload = {
            "client_id": self.client_id,
            "grant_type": "client_credentials",
        }
        
        try:
            logger.debug("Requesting access token from Tidal...")
            response = requests.post(
                url=refresh_url,
                data=payload,
                auth=(self.client_id, self.client_secret),
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                token_data = response.json()
                logger.debug("Access token obtained successfully")
                return token_data.get("access_token")
            else:
                logger.error(f"Failed to get access token: HTTP {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting access token: {e}")
            return None

    def search_tracks(self, query):
        """
        Search for tracks on Tidal.
        
        Args:
            query: Search query string
            
        Returns:
            dict: Search results with track items
            
        Raises:
            Exception: If search fails
        """
        try:
            tidal_token = self.get_access_token()
            if not tidal_token:
                raise Exception("Failed to get access token")

            search_url = (
                f"https://api.tidal.com/v1/search/tracks"
                f"?query={query}&limit=25&offset=0&countryCode=US"
            )
            header = {"authorization": f"Bearer {tidal_token}"}

            logger.debug(f"Searching Tidal for: {query}")
            search_data = requests.get(
                url=search_url, 
                headers=header, 
                timeout=self.timeout
            )
            response_data = search_data.json()
            
            filtered_items = [
                {
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "isrc": item.get("isrc"),
                    "audioQuality": item.get("audioQuality"),
                    "mediaMetadata": item.get("mediaMetadata"),
                    "album": item.get("album", {}),
                    "artists": item.get("artists", []),
                    "artist": item.get("artist", {}),
                    "trackNumber": item.get("trackNumber"),
                    "volumeNumber": item.get("volumeNumber"),
                    "duration": item.get("duration"),
                    "copyright": item.get("copyright"),
                    "explicit": item.get("explicit")
                }
                for item in response_data.get("items", [])
            ]
            
            logger.debug(f"Found {len(filtered_items)} tracks")
            
            return {
                "limit": response_data.get("limit"),
                "offset": response_data.get("offset"),
                "totalNumberOfItems": response_data.get("totalNumberOfItems"),
                "items": filtered_items
            }

        except Exception as e:
            logger.error(f"Search error: {e}")
            raise Exception(f"Search error: {str(e)}")

    def get_track_info(self, query, isrc=None):
        """
        Get detailed track information from search results.
        
        Args:
            query: Search query
            isrc: Optional ISRC code for precise matching
            
        Returns:
            dict: Track information
            
        Raises:
            Exception: If track not found or search fails
        """
        logger.info(f"Fetching track info: {query}" + (f" (ISRC: {isrc})" if isrc else ""))
        
        try:
            result = self.search_tracks(query)
            
            if not result or not result.get("items"):
                raise Exception(f"No tracks found for query: {query}")
            
            selected_track = None
            
            if isrc:
                isrc_items = [
                    item for item in result["items"] 
                    if item.get("isrc") == isrc
                ]
                
                if len(isrc_items) > 1:
                    logger.debug(f"Found {len(isrc_items)} tracks with ISRC {isrc}, selecting best quality")
                    hires_items = []
                    for item in isrc_items:
                        media_metadata = item.get("mediaMetadata", {})
                        tags = media_metadata.get("tags", []) if media_metadata else []
                        if "HIRES_LOSSLESS" in tags:
                            hires_items.append(item)
                    
                    selected_track = hires_items[0] if hires_items else isrc_items[0]
                elif len(isrc_items) == 1:
                    selected_track = isrc_items[0]
                else:
                    logger.warning(f"No tracks found with ISRC {isrc}, using first result")
                    selected_track = result["items"][0]
            else:
                selected_track = result["items"][0]
                
            if not selected_track:
                raise Exception(f"Track not found: {query}" + (f" (ISRC: {isrc})" if isrc else ""))
                
            title = selected_track.get('title', 'Unknown')
            quality = selected_track.get('audioQuality', 'Unknown')
            logger.info(f"Found track: {title} ({quality})")
            
            return selected_track
            
        except Exception as e:
            logger.error(f"Error getting track info: {e}")
            raise Exception(f"Error getting track info: {str(e)}")

    def get_download_url(self, track_id, quality="LOSSLESS"):
        """
        Get download URL for a track.
        
        Args:
            track_id: Tidal track ID
            quality: Audio quality (LOSSLESS, HI_RES, etc.)
            
        Returns:
            dict: Download URL and track info
            
        Raises:
            Exception: If URL cannot be obtained
        """
        logger.info(f"Fetching download URL for track {track_id}...")
        download_api_url = f"{self.api_url}/track/?id={track_id}&quality={quality}"
        
        try:
            logger.debug(f"API request: {download_api_url}")
            response = requests.get(download_api_url, timeout=self.timeout)
            
            if response.status_code == 200:
                data = response.json()
                
                for item in data:
                    if "OriginalTrackUrl" in item:
                        logger.info("Download URL obtained successfully")
                        return {
                            "download_url": item["OriginalTrackUrl"],
                            "track_info": data[0] if data else {}
                        }
                
                raise Exception("Download URL not found in response")
            else:
                raise Exception(f"API returned status code: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Error getting download URL: {e}")
            raise Exception(f"Error getting download URL: {str(e)}")

    def download_album_art(self, album_id, size="1280x1280"):
        """
        Download album artwork.
        
        Args:
            album_id: Tidal album ID
            size: Image size (e.g., "1280x1280")
            
        Returns:
            bytes: Image data or None if failed
        """
        try:
            art_url = f"https://resources.tidal.com/images/{album_id.replace('-', '/')}/{size}.jpg"
            logger.debug(f"Downloading album art from: {art_url}")
            
            response = requests.get(art_url, timeout=self.timeout)
            
            if response.status_code == 200:
                logger.debug("Album art downloaded successfully")
                return response.content
            else:
                logger.warning(f"Failed to download album art: HTTP {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Error downloading album art: {e}")
            return None

    def download_file(self, url, filepath, is_paused_callback=None, is_stopped_callback=None):
        """
        Download file from URL with retry logic.
        
        Args:
            url: Download URL
            filepath: Destination file path
            is_paused_callback: Optional callback to check if paused
            is_stopped_callback: Optional callback to check if stopped
            
        Returns:
            dict: Download result with success status and size
            
        Raises:
            Exception: If download fails after all retries
        """
        file_dir = os.path.dirname(filepath)
        if file_dir and not os.path.exists(file_dir):
            os.makedirs(file_dir, exist_ok=True)
            logger.debug(f"Created directory: {file_dir}")
        
        temp_filepath = filepath + ".part"
        retry_count = 0
        
        while retry_count <= self.max_retries:
            try:
                logger.debug(f"Downloading file (attempt {retry_count + 1}/{self.max_retries + 1})...")
                response = requests.get(url, timeout=60.0)
                
                if response.status_code != 200:
                    raise Exception(f"HTTP {response.status_code}")
                
                if is_stopped_callback and is_stopped_callback():
                    raise Exception("Download stopped")
                    
                while is_paused_callback and is_paused_callback():
                    time.sleep(0.1)
                    if is_stopped_callback and is_stopped_callback():
                        raise Exception("Download stopped")
                
                with open(temp_filepath, 'wb') as f:
                    f.write(response.content)
                
                downloaded_size = len(response.content)
                logger.info(f"Downloaded {downloaded_size / (1024 * 1024):.2f} MB")
                
                if self.progress_callback:
                    self.progress_callback(downloaded_size, downloaded_size)
                    
                os.rename(temp_filepath, filepath)
                logger.info("Download complete")
                return {"success": True, "size": downloaded_size}
                
            except Exception as e:
                retry_count += 1
                if retry_count > self.max_retries:
                    if os.path.exists(temp_filepath):
                        try:
                            os.remove(temp_filepath)
                            logger.debug("Removed temporary file")
                        except Exception:
                            pass
                    logger.error(f"Download failed after {self.max_retries} retries: {e}")
                    raise Exception(f"Download error after {self.max_retries} retries: {str(e)}")
                
                logger.warning(f"Download error (attempt {retry_count}/{self.max_retries}): {e}")
                logger.info(f"Retrying in {retry_count * 2} seconds...")
                time.sleep(retry_count * 2)

    def embed_metadata(self, filepath, track_info, search_info=None):
        """
        Embed metadata and album art into FLAC file.
        
        Args:
            filepath: Path to FLAC file
            track_info: Track metadata from download API
            search_info: Additional metadata from search API
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logger.info("Embedding metadata...")
            audio = FLAC(filepath)
            audio.clear()
            audio.clear_pictures()
            
            # Title
            if track_info.get("title"):
                audio["TITLE"] = track_info["title"]
            
            # Artists
            artists_list = []
            if search_info and search_info.get("artists"):
                for artist in search_info["artists"]:
                    if artist.get("name"):
                        artists_list.append(artist["name"])
            elif search_info and search_info.get("artist") and search_info["artist"].get("name"):
                artists_list.append(search_info["artist"]["name"])
            elif track_info.get("artists"):
                for artist in track_info["artists"]:
                    if artist.get("name"):
                        artists_list.append(artist["name"])
            elif track_info.get("artist") and track_info["artist"].get("name"):
                artists_list.append(track_info["artist"]["name"])
            
            if artists_list:
                audio["ARTIST"] = artists_list[0]
                if len(artists_list) > 1:
                    audio["ALBUMARTIST"] = "; ".join(artists_list)
                else:
                    audio["ALBUMARTIST"] = artists_list[0]
            
            # Album
            album_info = (
                search_info.get("album", {}) if search_info 
                else track_info.get("album", {})
            )
            if album_info.get("title"):
                audio["ALBUM"] = album_info["title"]
            
            # Track number
            track_number = (
                search_info.get("trackNumber") if search_info 
                else track_info.get("trackNumber")
            )
            if track_number:
                audio["TRACKNUMBER"] = str(track_number)
            
            # Disc number
            volume_number = (
                search_info.get("volumeNumber") if search_info 
                else track_info.get("volumeNumber")
            )
            if volume_number:
                audio["DISCNUMBER"] = str(volume_number)
            
            # Duration
            duration = (
                search_info.get("duration") if search_info 
                else track_info.get("duration")
            )
            if duration:
                audio["LENGTH"] = str(duration)
            
            # ISRC
            isrc = search_info.get("isrc") if search_info else track_info.get("isrc")
            if isrc:
                audio["ISRC"] = isrc
            
            # Copyright
            copyright_info = (
                search_info.get("copyright") if search_info 
                else track_info.get("copyright")
            )
            if copyright_info:
                audio["COPYRIGHT"] = copyright_info
            
            # Release date
            if album_info.get("releaseDate"):
                audio["DATE"] = album_info["releaseDate"][:4]
                try:
                    audio["YEAR"] = album_info["releaseDate"][:4]
                except Exception:
                    pass
            
            # Genre
            if track_info.get("genre"):
                audio["GENRE"] = track_info["genre"]
            
            # Audio quality comment
            if track_info.get("audioQuality"):
                audio["COMMENT"] = f"Tidal {track_info['audioQuality']}"
            
            # Album art
            if album_info.get("cover"):
                logger.debug("Downloading and embedding album art...")
                album_art = self.download_album_art(album_info["cover"])
                if album_art:
                    picture = Picture()
                    picture.data = album_art
                    picture.type = PictureType.COVER_FRONT
                    picture.mime = "image/jpeg"
                    picture.desc = "Cover"
                    audio.add_picture(picture)
                    logger.info("Album art embedded")
            
            audio.save()
            logger.info(f"Metadata embedded successfully for: {track_info.get('title', 'Unknown')}")
            return True
            
        except Exception as e:
            logger.error(f"Error embedding metadata: {e}", exc_info=True)
            return False

    def download(self, query, isrc=None, output_dir=".", quality="LOSSLESS", 
                 is_paused_callback=None, is_stopped_callback=None, auto_fallback=False):
        """
        Download a track with optional auto-fallback to alternative APIs.
        
        Args:
            query: Search query
            isrc: Optional ISRC code
            output_dir: Output directory
            quality: Audio quality
            is_paused_callback: Optional pause check callback
            is_stopped_callback: Optional stop check callback
            auto_fallback: Enable automatic API fallback on failure
            
        Returns:
            str: Path to downloaded file
            
        Raises:
            Exception: If download fails
        """
        if output_dir != ".":
            try:
                os.makedirs(output_dir, exist_ok=True)
            except OSError as e:
                logger.error(f"Failed to create output directory: {e}")
                raise Exception(f"Directory error: {e}")
        
        if auto_fallback:
            apis = self.get_available_apis()
            if not apis:
                logger.warning("No APIs available for fallback, using current API")
                return self._download_single(
                    query, isrc, output_dir, quality, 
                    is_paused_callback, is_stopped_callback
                )
            
            last_error = None
            for i, api in enumerate(apis, 1):
                api_url = api.get('url')
                try:
                    logger.info(f"[Auto Fallback {i}/{len(apis)}] Trying: {api_url}")
                    
                    fallback_downloader = TidalDownloader(api_url=api_url)
                    fallback_downloader.set_progress_callback(self.progress_callback)
                    
                    result = fallback_downloader._download_single(
                        query, isrc, output_dir, quality, 
                        is_paused_callback, is_stopped_callback
                    )
                    
                    logger.info(f"✓ Success with: {api_url}")
                    return result
                    
                except Exception as e:
                    last_error = str(e)
                    logger.error(f"✗ Failed with {api_url}: {last_error[:80]}")
                    continue
            
            raise Exception(f"All {len(apis)} APIs failed. Last error: {last_error}")
        
        return self._download_single(
            query, isrc, output_dir, quality, 
            is_paused_callback, is_stopped_callback
        )
    
    def _download_single(self, query, isrc, output_dir, quality, 
                        is_paused_callback, is_stopped_callback):
        """
        Internal method to perform a single download attempt.
        
        Args:
            query: Search query
            isrc: Optional ISRC code
            output_dir: Output directory
            quality: Audio quality
            is_paused_callback: Optional pause check callback
            is_stopped_callback: Optional stop check callback
            
        Returns:
            str: Path to downloaded file
            
        Raises:
            Exception: If download fails
        """
        track_info = self.get_track_info(query, isrc)
        track_id = track_info.get("id")
        
        if not track_id:
            raise Exception("No track ID found")
        
        # Extract artist names
        artists_list = []
        if track_info.get("artists"):
            for artist in track_info["artists"]:
                if artist.get("name"):
                    artists_list.append(artist["name"])
        elif track_info.get("artist") and track_info["artist"].get("name"):
            artists_list.append(track_info["artist"]["name"])
        
        artist_name = ", ".join(artists_list) if artists_list else "Unknown Artist"
        artist_name = self.sanitize_filename(artist_name)
        track_title = self.sanitize_filename(track_info.get("title", f"track_{track_id}"))
        
        output_filename = os.path.join(output_dir, f"{artist_name} - {track_title}.flac")
        
        # Check if file already exists
        if os.path.exists(output_filename):
            file_size = os.path.getsize(output_filename)
            if file_size > 0:
                logger.info(
                    f"File already exists: {output_filename} "
                    f"({file_size / (1024 * 1024):.2f} MB)"
                )
                return output_filename
        
        # Get download URL
        download_info = self.get_download_url(track_id, quality)
        download_url = download_info["download_url"]
        download_track_info = download_info["track_info"]
        
        logger.info(f"Downloading to: {output_filename}")
        self.download_file(
            download_url, 
            output_filename, 
            is_paused_callback=is_paused_callback, 
            is_stopped_callback=is_stopped_callback
        )
        
        # Embed metadata
        logger.info("Adding metadata...")
        try:
            self.embed_metadata(output_filename, download_track_info, track_info)
            logger.info("Metadata saved successfully")
        except Exception as e:
            logger.error(f"Failed to embed metadata: {e}")
        
        logger.info("Download completed")
        return output_filename


def main():
    """Main function for testing the downloader."""
    logger.info("=== TidalDL - Tidal Downloader ===")
    
    selected_api = TidalDownloader.select_api_interactive()
    downloader = TidalDownloader(timeout=30, max_retries=3, api_url=selected_api)
    
    query = "APT."
    isrc = "USUM71027402"
    output_dir = "."
    
    try:
        downloaded_file = downloader.download(query, isrc, output_dir)
        logger.info(f"Success: File saved as {downloaded_file}")
    except Exception as e:
        logger.error(f"Download failed: {e}")


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
        
    main()