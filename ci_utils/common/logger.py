import logging
import threading

# Thread-local storage for test name
_test_name = threading.local()

# -----------------------
# Set current test name for logging
# -----------------------
def set_test_name(name):
    _test_name.value = name

# -----------------------
# Custom logging filter to add test name to log records
# -----------------------
class TestNameFilter(logging.Filter):
    def filter(self, record):
        record.testname = getattr(_test_name, "value", "logger")
        return True

# -----------------------
# Get configured logger
# -----------------------
def get_logger(name=__name__, level=logging.INFO):
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] [%(processName)s] [%(testname)s] %(message)s",
            datefmt="%H:%M:%S"
        )
        handler.setFormatter(formatter)
        handler.addFilter(TestNameFilter())
        logger.addHandler(handler)
        logger.propagate = False

    return logger