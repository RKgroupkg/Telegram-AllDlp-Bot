#  Copyright (c) 2025 Rkgroup.
#  Quick Dl is an open-source Downloader bot licensed under MIT.
#  All rights reserved where applicable.
#
#

from typing import Union
from pyrate_limiter import (
    BucketFullException,
    Duration,
    Limiter,
    MemoryListBucket,
    RequestRate,
)


class RateLimiter:
    """
    Implement rate limit logic using leaky bucket
    algorithm, via pyrate_limiter library.
    (https://pypi.org/project/pyrate-limiter/)
    """

    def __init__(
        self,
        limit_sec: int,
        limit_min: int,
        interval_sec: int = Duration.SECOND,
        interval_min: int = Duration.MINUTE,
    ) -> None:
        """Request rate definition.

        Args:
            limit_sec: Number of requests allowed within ``interval``
            limit_min: Number of requests allowed within ``interval``
            interval_sec: Time interval, in seconds
            interval_min: Time interval, in sec but for larger time

        """

        # 2 requests per seconds (default).
        self.second_rate = RequestRate(limit_sec, interval_sec)

        # 19 requests per minute (default).
        self.minute_rate = RequestRate(limit_min, interval_min)

        self.limiter = Limiter(
            self.second_rate, self.minute_rate, bucket_class=MemoryListBucket
        )

    async def acquire(self, update_id: Union[int, str]) -> bool:
        """
        Acquire rate limit per update_id and return True / False
        based on update_id ratelimit status.

        params:
            update_id (int | str): unique identifier for update.

        returns:
            bool: True if update_id is ratelimited else False.
        """

        try:
            self.limiter.try_acquire(update_id)
            return False
        except BucketFullException:
            return True
