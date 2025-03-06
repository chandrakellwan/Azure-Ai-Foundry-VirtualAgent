import multiprocessing
import os
import sys
import json
from typing import Dict
import asyncio
import logging
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import FilePurpose, FileSearchTool, AsyncToolSet, Agent
from azure.identity import DefaultAzureCredential

from dotenv import load_dotenv

load_dotenv()

# Create a central logger for the application
logger = logging.getLogger("azureaiapp")
logger.setLevel(logging.INFO)

# Configure the stream handler (stdout)
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setLevel(logging.INFO)
stream_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
stream_handler.setFormatter(stream_formatter)
logger.addHandler(stream_handler)

# Configure logging to file, if log file name is provided
log_file_name = os.getenv("APP_LOG_FILE", "")
if log_file_name != "":
    file_handler = logging.FileHandler(log_file_name)
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

FILES_NAMES = ["product_info_1.md", "product_info_2.md"]

async def create_agent(ai_client: AIProjectClient) -> Agent:
    files: Dict[str, Dict[str, str]] = {}

    # Create a new agent with the required resources
    logger.info("Creating new agent with resources")

    # Upload files for file search
    for file_name in FILES_NAMES:
        file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'files', file_name))
        file = await ai_client.agents.upload_file_and_poll(file_path=file_path, purpose=FilePurpose.AGENTS)
        # Store both file id and the file path using the file name as key.
        files[file_name] = {"id": file.id, "path": file_path}

    # Serialize and store files information in the environment variable (so workers see it)
    os.environ["UPLOADED_FILE_MAP"] = json.dumps(files)
    logger.info(f"Set env UPLOADED_FILE_MAP = {os.environ['UPLOADED_FILE_MAP']}")

    # Create the vector store using the file IDs.
    vector_store = await ai_client.agents.create_vector_store_and_poll(
        file_ids=[info["id"] for info in files.values()],
        name="sample_store"
    )
    logger.info("agent: file store and vector store success")

    file_search_tool = FileSearchTool(vector_store_ids=[vector_store.id])
    toolset = AsyncToolSet()
    toolset.add(file_search_tool)

    agent = await ai_client.agents.create_agent(
        model=os.environ["AZURE_AI_AGENT_DEPLOYMENT_NAME"],
        name=os.environ["AZURE_AI_AGENT_NAME"], 
        instructions="You are helpful assistant",
        toolset=toolset
    )
    return agent


async def update_agent(agent: Agent, ai_client: AIProjectClient) -> Agent:
    logger.info("Updating agent with resources")
    files: Dict[str, Dict[str, str]] = {}

    # Upload files for file search
    for file_name in FILES_NAMES:
        file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'files', file_name))
        file = await ai_client.agents.upload_file_and_poll(file_path=file_path, purpose=FilePurpose.AGENTS)
        # Store both file id and the file path using the file name as key.
        files[file_name] = {"id": file.id, "path": file_path}

    # Serialize and store files information in the environment variable (so workers see it)
    os.environ["UPLOADED_FILE_MAP"] = json.dumps(files)
    logger.info(f"Set env UPLOADED_FILE_MAP = {os.environ['UPLOADED_FILE_MAP']}")

    # Create the vector store using the file IDs.
    vector_store = await ai_client.agents.create_vector_store_and_poll(
        file_ids=[info["id"] for info in files.values()],
        name="sample_store"
    )
    logger.info("agent: file store and vector store success")

    file_search_tool = FileSearchTool(vector_store_ids=[vector_store.id])
    toolset = AsyncToolSet()
    toolset.add(file_search_tool)

    agent = await ai_client.agents.update_agent(
        assistant_id=agent.id,
        model=os.environ["AZURE_AI_AGENT_DEPLOYMENT_NAME"],
        name=os.environ["AZURE_AI_AGENT_NAME"],
        instructions="You are helpful assistant",
        toolset=toolset
    )
    return agent


async def initialize_resources():
    try:
        ai_client = AIProjectClient.from_connection_string(
            credential=DefaultAzureCredential(exclude_shared_token_cache_credential=True),
            conn_str=os.environ["AZURE_AIPROJECT_CONNECTION_STRING"],
        )

        # If the environment already has AZURE_AI_AGENT_ID, try fetching that agent
        if os.environ.get("AZURE_AI_AGENT_ID") is not None:
            try: 
                agent = await ai_client.agents.get_agent(os.environ["AZURE_AI_AGENT_ID"])
                logger.info(f"Found agent by ID: {agent.id}")
                # Update the agent with the latest resources
                agent = await update_agent(agent, ai_client)
                return
            except Exception as e:
                logger.warning(f"Could not retrieve agent by AZURE_AI_AGENT_ID = {os.environ['AZURE_AI_AGENT_ID']}, error: {e}")

        # Check if an agent with the same name already exists
        agent_list = await ai_client.agents.list_agents()
        if agent_list.data:
            for agent_object in agent_list.data:
                if agent_object.name == os.environ["AZURE_AI_AGENT_NAME"]:
                    logger.info(f"Found existing agent named '{agent_object.name}', ID: {agent_object.id}")
                    os.environ["AZURE_AI_AGENT_ID"] = agent_object.id
                    # Update the agent with the latest resources
                    agent = await update_agent(agent_object, ai_client)
                    return

        # Create a new agent
        agent = await create_agent(ai_client)
        os.environ["AZURE_AI_AGENT_ID"] = agent.id
        logger.info(f"Created agent, agent ID: {agent.id}")

    except Exception as e:
        logger.info("Error creating agent: {e}", exc_info=True)
        raise RuntimeError(f"Failed to create the agent: {e}")

def on_starting(server):
    """This code runs once before the workers will start."""
    asyncio.get_event_loop().run_until_complete(initialize_resources())

max_requests = 1000
max_requests_jitter = 50
log_file = "-"
bind = "0.0.0.0:50505"

if not os.getenv("RUNNING_IN_PRODUCTION"):
    reload = True

preload_app = True
num_cpus = multiprocessing.cpu_count()
workers = (num_cpus * 2) + 1
worker_class = "uvicorn.workers.UvicornWorker"

timeout = 120
