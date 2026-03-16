import os
import json
from ci_utils.common.duffy_client import DuffySession

from ci_utils.common.logger import get_logger
from ci_utils.common.retry import retry_func
logger = get_logger(__name__)

WORKSPACE = os.getenv("WORKSPACE", "/tmp")
SESSION_FILE = os.path.join(WORKSPACE, "duffy_session.json")
BAREMETAL_SESSION_FILE = os.path.join(WORKSPACE, "baremetal_duffy_session.json")
BAREMETAL_NODES = os.getenv("BAREMETAL_NODES", "false").lower()

reserved_session = None

@retry_func(
    retry_on=(RuntimeError,),
    retry_interval=120,
    timeout=3600
)
def reserve_nodes(server_count=1, client_count=1):
    """
    Reserve server and client nodes separately and store in JSON.
    
    Args:
        server_count (int): Number of server nodes to reserve
        client_count (int): Number of client nodes to reserve
    
    Returns:
        dict: {"servers": [...], "clients": [...]}
    """
    global reserved_session

    logger.info("Starting node reservation...")
    
    # Initialize Duffy session
    if BAREMETAL_NODES == "true":
        session = DuffySession(workspace=WORKSPACE, metal_only=True)
        session_file = BAREMETAL_SESSION_FILE
    else:
        session = DuffySession(workspace=WORKSPACE, node_count=server_count + client_count)
        session_file = SESSION_FILE

    # Reserve nodes
    nodes = session.create()
    logger.info("Total reserved nodes: %s", nodes)

    # Segregate nodes into server and client lists
    if len(nodes) < server_count + client_count:
        raise RuntimeError(
            f"Not enough nodes reserved. Requested: "
            f"{server_count} servers + {client_count} clients, got {len(nodes)} nodes"
        )

    servers = nodes[:server_count]
    clients = nodes[server_count:server_count + client_count]

    node_info = {
        "session_id": str(session.session_id),
        "servers": servers,
        "clients": clients
    }

    # Save JSON for other tests to consume
    with open(session_file, "w") as f:
        json.dump(node_info, f, indent=2)

    reserved_session = session
    return node_info

def delete_nodes():
    """
    Delete the reserved nodes stored in the session JSON file.
    Called after all tests finish (teardown).
    Safe to call even if no session file exists.
    """

    session_file = BAREMETAL_SESSION_FILE if BAREMETAL_NODES == "true" else SESSION_FILE

    if not os.path.exists(session_file):
        logger.warning(f"No session file '{session_file}' found. Nothing to delete.")
        return

    logger.info(f"Reading session file '{session_file}'")

    try:
        with open(session_file, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        logger.error(f"Corrupted session file '{session_file}'. Cannot delete nodes.")
        return

    session_id = data.get("session_id")
    nodes = data.get("nodes", [])

    if not session_id:
        logger.error(f"No valid session_id in '{session_file}'. Cannot delete nodes.")
        return

    logger.info(f"Releasing session {session_id} with nodes: {nodes}")

    # If the in-memory session exists, use it (recommended)
    global reserved_session
    if reserved_session and reserved_session.session_id == int(session_id):
        try:
            reserved_session.delete()
            logger.info("Nodes released via active DuffySession instance.")
        except Exception as e:
            logger.exception(f"Failed to release nodes: {e}")

    else:
        # Session was lost; recreate a DuffySession object
        session = DuffySession(workspace=WORKSPACE)
        session.session_id = int(session_id)
        try:
            session.delete()
            logger.info("Nodes released via reconstructed session.")
        except Exception as e:
            logger.exception(f"Failed to release nodes: {e}")

    # Remove session file
    try:
        os.remove(session_file)
        logger.info(f"Deleted session file '{session_file}'.")
    except Exception as e:
        logger.warning(f"Could not delete session file '{session_file}': {e}")