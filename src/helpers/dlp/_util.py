
def format_size(size_bytes):
    """Format file size in human readable format"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes/1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes/(1024*1024):.1f} MB"
    else:
        return f"{size_bytes/(1024*1024*1024):.1f} GB"

def format_time(seconds):
    """Format time in human readable format"""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        minutes = seconds // 60
        seconds %= 60
        return f"{minutes:.0f}m {seconds:.0f}s"
    else:
        hours = seconds // 3600
        seconds %= 3600
        minutes = seconds // 60
        seconds %= 60
        return f"{hours:.0f}h {minutes:.0f}m"

def truncate_text(text: str, max_length: int = 40) -> str:
    """
    Truncate text to a specified max length with ellipsis
    """
    return text[:max_length] + '...' if len(text) > max_length else text

def format_duration(seconds: int) -> str:
    """Format duration in seconds to a readable string"""
    if not seconds:
        return "Unknown"
        
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    
    if hours:
        return f"{hours}:{int(minutes):02d}:{int(seconds):02d}"
    else:
        return f"{minutes}:{int(seconds):02d}"
    
