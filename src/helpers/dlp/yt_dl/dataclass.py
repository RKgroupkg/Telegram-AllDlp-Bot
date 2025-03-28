#  Copyright (c) 2025 Rkgroup.
#  Quick Dl is an open-source Downloader bot licensed under MIT.
#  All rights reserved where applicable.
#
#

from typing import Optional ,List,Literal,Dict,Any
from pydantic import BaseModel, Field
import os

class DownloadInfo(BaseModel):
    """
    Represents comprehensive download information with optional fields.
    """
    success: bool = True
    id: Optional[str] = None
    url: Optional[str] = None
    file_path: Optional[str] = None
    title: Optional[str] = None
    performer: Optional[str] = None
    thumbnail: Optional[str] = None
    ext: Optional[str] = None
    filesize: Optional[int] = None
    duration: Optional[int] = None
    error: Optional[str] = None


class SearchInfo(BaseModel):
    """
    Info of video 
    """
    success: bool = True
    id: Optional[str] = None
    title: Optional[str] = None
    duration: Optional[int] = None
    thumbnail: Optional[str] = None
    uploader: Optional[str] = "Unknown"
    view_count: Optional[int] = 0
    cache_dir: str = "/tmp/"
    upload_date: Optional[str] = ""
    description: Optional[str] = ""
    formats: Optional[List] = None
    all_formats: Optional[List] = None
    video_formats: Optional[List] = None
    audio_formats: Optional[List] = None
    combined_formats: Optional[List] = None


class PlaylistSearchResult(BaseModel):
    id: str
    title: str = 'Unknown Playlist'
    url: str
    thumbnail: Optional[str] = None
    type: Literal['playlist'] = 'playlist'
    entries_count: int = 0
    uploader: str = 'Unknown'


class VideoSearchResult(BaseModel):
    id: str
    title: str = 'Unknown Title'
    url: str
    thumbnail: Optional[str] = None
    duration: int = 0
    duration_string: str
    uploader: str = 'Unknown'
    uploader_id: str = 'Unknown'
    description: str = ''
    view_count: int = 0
    upload_date: str
    type: Literal['video'] = 'video'
    live_status: Optional[str] = None
    exceeds_max_length: Optional[bool] = None

# class CallBackData(BaseModel):
#     type: Optional[str] = None
#     video_id: Optional[str] = None
#     format_id: Optional[Dict[str, Any]]