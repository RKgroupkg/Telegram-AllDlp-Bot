import http.client
import json
import time
import random

import os
from dataclasses import dataclass
from typing import List, Dict, Optional, Union, Tuple, Any
from urllib.parse import quote
from src.logging import LOGGER



@dataclass
class APIKey:
    key: str
    host: str
    remaining_requests: int = 100
    reset_time: Optional[float] = None
    is_active: bool = True

class InstagramDownloader:
    def __init__(self, api_keys: List[Dict[str, str]], max_retries: int = 3, 
                 retry_delay: int = 2, timeout: int = 30):
        self.api_keys = [APIKey(key=k['key'], host=k['host']) for k in api_keys]
        if not self.api_keys:
            raise ValueError("At least one API key is required")
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.current_key_index = 0
        LOGGER(__name__).info(f"Initialized with {len(self.api_keys)} API keys")
    
    def _get_next_available_key(self) -> Optional[APIKey]:
        start_index = self.current_key_index
        current_time = time.time()
        for key in self.api_keys:
            if key.reset_time and key.reset_time <= current_time:
                key.remaining_requests = 100
                key.reset_time = None
                key.is_active = True
        for _ in range(len(self.api_keys)):
            self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
            key = self.api_keys[self.current_key_index]
            if key.is_active and key.remaining_requests > 0:
                return key
            if self.current_key_index == start_index:
                break
        next_reset = min((k.reset_time for k in self.api_keys if k.reset_time), default=None)
        if next_reset:
            wait_time = next_reset - current_time
            if wait_time <= 10:
                LOGGER(__name__).info(f"All keys at limit, waiting {wait_time:.2f}s for reset")
                time.sleep(wait_time + 0.5)
                return self._get_next_available_key()
        LOGGER(__name__).warning("No available API keys found")
        return None
    
    def _update_key_status(self, key: APIKey, headers: Dict[str, str], status_code: int):
        remaining = headers.get('x-ratelimit-requests-remaining') or headers.get('x-ratelimit-remaining')
        if remaining:
            try:
                key.remaining_requests = int(remaining)
            except ValueError:
                LOGGER(__name__).warning(f"Invalid remaining requests value: {remaining}")
        if status_code == 429:
            reset_after = headers.get('x-ratelimit-reset') or headers.get('retry-after')
            if reset_after:
                try:
                    reset_seconds = float(reset_after)
                    key.reset_time = time.time() + reset_seconds
                    key.remaining_requests = 0
                    LOGGER(__name__).info(f"API key rate limited, will reset after {reset_seconds}s")
                except ValueError:
                    key.reset_time = time.time() + 300
                    key.remaining_requests = 0
            else:
                key.reset_time = time.time() + 60
                key.remaining_requests = 0
        elif status_code >= 400:
            key.remaining_requests = max(0, key.remaining_requests - 1)
            if status_code >= 500:
                pass
            elif status_code in (401, 403):
                LOGGER(__name__).error(f"API key authentication failed: {key.key[:5]}...")
                key.is_active = False
    
    def _make_request(self, endpoint: str, url: str) -> Tuple[Optional[Dict], int]:
        api_key = self._get_next_available_key()
        if not api_key:
            LOGGER(__name__).error("No available API keys to make request")
            return None, 0
        encoded_url = quote(url, safe='')
        conn = http.client.HTTPSConnection(api_key.host, timeout=self.timeout)
        headers = {
            'x-rapidapi-key': api_key.key,
            'x-rapidapi-host': api_key.host
        }
        full_endpoint = f"/{endpoint}?url={encoded_url}"
        try:
            LOGGER(__name__).debug(f"Making request to {api_key.host}{full_endpoint}")
            conn.request("GET", full_endpoint, headers=headers)
            response = conn.getresponse()
            status_code = response.status
            self._update_key_status(api_key, dict(response.getheaders()), status_code)
            if status_code == 200:
                data = response.read().decode("utf-8")
                try:
                    return json.loads(data), status_code
                except json.JSONDecodeError:
                    LOGGER(__name__).error("Failed to parse JSON response")
                    return None, status_code
            else:
                LOGGER(__name__).warning(f"Request failed with status code: {status_code}")
                return None, status_code
        except Exception as e:
            LOGGER(__name__).error(f"Request error: {str(e)}")
            return None, 0
        finally:
            conn.close()
    
    def download(self, url: str) -> Dict[str, Any]:
        LOGGER(__name__).info(f"Downloading content from: {url}")
        for attempt in range(1, self.max_retries + 1):
            response_data, status_code = self._make_request("post-dl", url)
            if response_data and status_code == 200 and response_data.get('status', False):
                data = response_data.get('data', {})
                if data:
                    LOGGER(__name__).info(f"Successfully retrieved data for {url}")
                    return data
                else:
                    LOGGER(__name__).warning("No data found in response")
                    return {}
            else:
                LOGGER(__name__).warning(f"Attempt {attempt} failed with status {status_code}")
            if attempt < self.max_retries:
                delay = self.retry_delay * (2 ** (attempt - 1))
                jitter = random.uniform(0, 0.5 * delay)
                LOGGER(__name__).info(f"Retrying in {delay + jitter:.2f}s (attempt {attempt}/{self.max_retries})")
                time.sleep(delay + jitter)
        LOGGER(__name__).error(f"Failed to download after {self.max_retries} attempts")
        return {}

def get_instagram_post_data(post_url: str, api_keys: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    if not api_keys:
        env_keys = os.environ.get('INSTAGRAM_API_KEYS')
        if env_keys:
            try:
                api_keys = json.loads(env_keys)
            except json.JSONDecodeError:
                LOGGER(__name__).error("Invalid INSTAGRAM_API_KEYS environment variable format")
                api_keys = []
    downloader = InstagramDownloader(api_keys)
    return downloader.download(post_url)

if __name__ == "__main__":
    api_keys = [
        {
            'key': 'xx266314xxxxxxxpx8b436jsnxxxxx40xx', # your api_id as key
            'host': 'instagram-looter2.p.rapidapi.com'
        }
    ]
    post_url = "https://www.instagram.com/p/CqIbCzYMi5C/"
    post_data = get_instagram_post_data(post_url, api_keys)
    print(post_data)