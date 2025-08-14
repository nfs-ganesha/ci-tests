# tests/test_delete_nodes.py
import os
import pytest
import json
from ci_utils.common.duffy_client import DuffySession
from ci_utils.common.logger import get_logger, set_test_name

logger = get_logger(__name__)

WORKSPACE = os.getenv("WORKSPACE", "/tmp")
SESSION_FILE = os.path.join(WORKSPACE, "duffy_session.json")
BAREMETAL_SESSION_FILE = os.path.join(WORKSPACE, "baremetal_duffy_session.json")
BAREMETAL_NODES = os.getenv("BAREMETAL_NODES", "false").lower()

@pytest.fixture(autouse=True)
def attach_test_name(request):
    set_test_name(request.node.name)

# -------------------------------
# Helper function to release nodes
# -------------------------------
def release_session_file(session_file: str):
    if not os.path.exists(session_file):
        logger.warning("Session file '%s' does not exist. Nothing to release.", session_file)
        return

    with open(session_file, "r") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            logger.error("Failed to parse session file '%s'. Cannot release nodes.", session_file)
            return

    session_id = data.get("session_id")
    nodes = data.get("nodes", [])

    if not session_id:
        logger.error("No session_id found in session file '%s'. Cannot release nodes.", session_file)
        return

    if not nodes:
        logger.warning("Session '%s' has no nodes recorded. Nothing to release.", session_id)
        return

    logger.info("Releasing session '%s' with nodes: %s", session_id, nodes)

    session = DuffySession(workspace=WORKSPACE)
    session.session_id = int(session_id)  # attach existing session

    try:
        session.delete()
        logger.info("Released nodes successfully for session '%s'.", session_id)
    except Exception as e:
        logger.exception("Failed to release nodes for session '%s': %s", session_id, e)

    try:
        os.remove(session_file)
        logger.info("Deleted session file '%s'.", session_file)
    except OSError as e:
        logger.warning("Could not delete session file '%s': %s", session_file, e)

# -------------------------------
# Test to release nodes
# -------------------------------
def test_release_nodes():
    """Release node(s) reserved for tests."""
    logger.info("[TEST START]: Starting node release...")
    if BAREMETAL_NODES == "true":
        release_session_file(BAREMETAL_SESSION_FILE)
    else:
        release_session_file(SESSION_FILE)
