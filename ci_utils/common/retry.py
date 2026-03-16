import time
import functools
from ci_utils.common.logger import get_logger
logger = get_logger(__name__)

def retry_func(retry_on=(Exception,), retry_interval=60, timeout=3600):
    """
    Generic retry decorator.
    Retries only for specified exception types.
    """

    def decorator(func):

        @functools.wraps(func)
        def wrapper(*args, **kwargs):

            start_time = time.time()

            while True:
                try:
                    return func(*args, **kwargs)

                except retry_on as e:

                    elapsed = time.time() - start_time

                    if elapsed >= timeout:
                        logger.error("Retry timeout reached")
                        raise

                    logger.warning(
                        "Retryable error occurred: %s. Retrying in %s seconds...",
                        str(e),
                        retry_interval,
                    )

                    time.sleep(retry_interval)

        return wrapper

    return decorator