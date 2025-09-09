import os
import json
import pytest
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
# Test to reserve nodes
# -------------------------------
def test_reserve_nodes():
    """
    Reserve node(s) at the start and save session info.
    Only reserve once per CI run.
    """
    logger.info("[TEST START]: Starting node reservation...")
    if BAREMETAL_NODES == "true":
        session = DuffySession(workspace=WORKSPACE, metal_only=True)
        session_file = BAREMETAL_SESSION_FILE
    else:
        session = DuffySession(workspace=WORKSPACE)
        session_file = SESSION_FILE
    
    logger.info("Duffy session initialized with workspace: %s", WORKSPACE)
    nodes = session.create()
    logger.info("Reserved node(s): %s", nodes)

    # Save session info for parallel tests to consume
    with open(session_file, "w") as f:
        json.dump({
            "session_id": str(session.session_id),
            "nodes": nodes
        }, f)

    global reserved_session
    reserved_session = session

