import csv
import json
import os
import random
from datetime import datetime, timezone
from pathlib import Path

import psutil
from locust import HttpUser, between, events, task

from mxtoai._logging import get_logger

# Configure logger
logger = get_logger("load_test")

# Get script directory
SCRIPT_DIR = Path(__file__).parent
TEST_FILES_DIR = SCRIPT_DIR / "test_files"
STATS_FILE = SCRIPT_DIR / "system_stats.csv"


def get_random_test_files(num_files: int = 2) -> list[str]:
    """Get random PDF files from test_files directory"""
    pdf_files = [str(p) for p in TEST_FILES_DIR.glob("*.pdf")]
    return random.sample(pdf_files, min(num_files, len(pdf_files)))


# Complex topics for testing
superficial_presets = [
    {
        "subject": "Understanding Quantum Supremacy and its Implications",
        "textContent": """Can you explain the concept of quantum supremacy and its potential impact on cryptography?
        I'm particularly interested in understanding how Shor's algorithm could potentially break current RSA encryption,
        and what post-quantum cryptography solutions are being developed. Also, how does quantum decoherence affect the
        stability of qubits in current quantum computers, and what approaches are being used to mitigate this issue?
        Please include information about error correction in quantum computing and the concept of quantum fault tolerance.""",
        "files": [],
    },
    {
        "subject": "Zero-Knowledge Proofs in Blockchain Privacy",
        "textContent": """I need a detailed explanation of how zero-knowledge proofs work in blockchain privacy solutions.
        Specifically, how do zk-SNARKs enable transaction privacy while maintaining verifiability? Could you explain the
        mathematical principles behind zero-knowledge proofs, including the concepts of completeness, soundness, and
        zero-knowledge? Also, how do recursive SNARKs work in scaling solutions, and what are the trade-offs between
        different types of zero-knowledge proof systems (SNARKs vs STARKs)? Please include real-world applications in
        privacy-focused blockchain platforms.""",
        "files": [],
    },
]

# Deep research topics
research_presets = [
    {
        "subject": "Latest Advancements in Large Language Models",
        "textContent": """Research the latest advancements in large language models, focusing on improvements in reasoning,
        factuality, and efficiency. What are the current state-of-the-art architectures? How do different training approaches
        like instruction tuning and RLHF impact model performance? What are the main challenges in reducing hallucinations
        and improving reliability? Include specific examples from recent research papers and industry implementations.""",
        "files": [],
    },
    {
        "subject": "Sustainable Computing and Green AI",
        "textContent": """Investigate current approaches to making AI more environmentally sustainable. What are the latest
        techniques for reducing the carbon footprint of large model training? How effective are methods like pruning,
        quantization, and distillation in reducing computational costs while maintaining performance? What are the
        trade-offs between model size, accuracy, and energy consumption? Include specific metrics and case studies.""",
        "files": [],
    },
]

# Test scenarios with weights
EMAIL_SCENARIOS = [
    {
        "weight": 40,  # 40% of requests will use this scenario
        "data": {
            "from_email": "test@example.com",
            "to": random.choice(["summarise@mxtoai.com", "eli5@mxtoai.com"]),
            **random.choice(superficial_presets),  # Use random complex topic
        },
    },
    {
        "weight": 15,  # 15% of requests
        "data": {"from_email": "test@example.com", "to": "translate@mxtoai.com", **random.choice(superficial_presets)},
    },
    {
        "weight": 15,  # 15% of requests
        "data": {
            "from_email": "test@example.com",
            "to": "ask@mxtoai.com",
            "subject": "Please find attachments",
            "textContent": random.choice(
                [
                    "Please analyse and summarise each of the attached documents",
                    "Please analyse and summarise each of the attached documents",
                    "Please analyse and leave detailed feedback about the formatting of each of the attached documents",
                ]
            ),
            "files": get_random_test_files(2),  # Two random PDF files
        },
    },
    # {
    #     "weight": 17,  # 17% deep research without files (increased from 15%)
    #     "data": {
    #         "from_email": "test@example.com",
    #         "to": "research@mxtoai.com",
    #         **random.choice(research_presets),
    #         "deep_research": True
    #     }
    # },
    # {
    #     "weight": 13,  # 13% deep research with files (increased from 10%)
    #     "data": {
    #         "from_email": "test@example.com",
    #         "to": "research@mxtoai.com",
    #         "subject": "Research with Attachments",
    #         "textContent": "Please conduct deep research on these documents and provide comprehensive findings.",
    #         "files": get_random_test_files(2),
    #         "deep_research": True
    #     }
    # }
]


# System resource monitoring
def get_system_stats() -> dict:
    """Get current system resource usage"""
    process = psutil.Process(os.getpid())
    return {
        "cpu_percent": process.cpu_percent(),
        "memory_percent": process.memory_percent(),
        "num_threads": process.num_threads(),
        "connections": len(process.net_connections()),
    }


# CSV writer for system stats
class SystemStatsWriter:
    def __init__(self, filename: str):
        self.filename = filename
        Path(filename).parent.mkdir(parents=True, exist_ok=True)
        self._file_handle = Path(filename).open("w", newline="")  # noqa: SIM115
        self.writer = csv.writer(self._file_handle)
        self.writer.writerow(["timestamp", "cpu_percent", "memory_percent", "num_threads", "connections"])

    def write_stats(self, stats: dict):
        self.writer.writerow(
            [
                datetime.now(timezone.utc).isoformat(),
                stats["cpu_percent"],
                stats["memory_percent"],
                stats["num_threads"],
                stats["connections"],
            ]
        )

    def close(self):
        if self._file_handle and not self._file_handle.closed:
            self._file_handle.close()


# Initialize system stats writer
stats_writer = SystemStatsWriter(str(STATS_FILE))


class EmailProcessingUser(HttpUser):
    wait_time = between(0.5, 1.5)  # Random wait between requests

    def on_start(self):
        """Setup before tests start"""
        # Initialize deep research tool
        # from mxtoai.tools.deep_research_tool import DeepResearchTool
        # self.deep_research_tool = DeepResearchTool(use_mock_service=True)
        # self.deep_research_tool.enable_deep_research()

        # Verify test files exist
        for scenario in EMAIL_SCENARIOS:
            for file_path_str in scenario["data"].get("files", []):
                if not Path(file_path_str).exists():
                    logger.warning(f"Test file not found: {file_path_str}")

    def _process_deep_research(self, data: dict) -> dict:
        """Process deep research request using mock service"""
        try:
            # Extract parameters for deep research
            query = data.get("textContent", "")
            context = data.get("subject", "")
            stream = data.get("stream", False)

            # Process attachments if present
            attachments = [
                {"path": file_path_str, "type": "application/pdf", "filename": Path(file_path_str).name}
                for file_path_str in data.get("files", [])
            ]

            # Call deep research tool with mock service
            result = self.deep_research_tool.forward(
                query=query, context=context, attachments=attachments, stream=stream
            )

        except Exception as e:
            logger.exception("Error in deep research processing")
            return {"status": "error", "message": str(e)}
        else:
            return {"status": "success", "message": "Research completed successfully", "data": result}

    @task
    def process_email(self):
        """Send email processing request based on weighted scenarios"""
        # Select scenario based on weights
        scenario = random.choices(EMAIL_SCENARIOS, weights=[s["weight"] for s in EMAIL_SCENARIOS], k=1)[0]

        # For the third scenario, get fresh random files each time
        if scenario["data"]["to"] == "full-analysis@mxtoai.com":
            scenario["data"]["files"] = get_random_test_files(2)

        # Check if this is a deep research request
        if scenario["data"].get("deep_research"):
            start_time = datetime.now(timezone.utc)
            result = self._process_deep_research(scenario["data"])
            end_time = datetime.now(timezone.utc)

            # Record response time for deep research
            response_time = (end_time - start_time).total_seconds() * 1000

            # Record system stats
            stats_writer.write_stats(get_system_stats())

            # Log the result
            if result["status"] == "success":
                events.request.fire(
                    request_type="Deep Research",
                    name=scenario["data"]["to"],
                    response_time=response_time,
                    response_length=len(json.dumps(result)),
                    exception=None,
                )
            else:
                events.request.fire(
                    request_type="Deep Research",
                    name=scenario["data"]["to"],
                    response_time=response_time,
                    response_length=0,
                    exception=result["message"],
                )
            return

        # Prepare the request data for regular email processing
        data = scenario["data"].copy()
        files = []

        # Add files if present in scenario
        for file_path_str in data.pop("files", []):
            try:
                file_path_obj = Path(file_path_str)
                opened_file = file_path_obj.open("rb")
                files.append(("files", (file_path_obj.name, opened_file, "application/pdf")))
            except FileNotFoundError:
                logger.error(f"File not found: {file_path_str}")
                continue

        try:
            # Send the request
            with self.client.post("/process-email", data=data, files=files, catch_response=True) as response:
                # Record system stats
                stats_writer.write_stats(get_system_stats())

                # Validate response
                if response.status_code == 200:
                    response_data = response.json()
                    if (
                        response_data.get("message") == "Email received and queued for processing"
                        and response_data.get("status") == "processing"
                    ):
                        response.success()
                    else:
                        response.failure(f"Unexpected response: {response_data}")
                else:
                    response.failure(f"HTTP {response.status_code}: {response.text}")

        finally:
            # Clean up file handles
            for _, file_tuple in files:
                file_tuple[1].close()


# Event handlers for test lifecycle
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when a test is starting"""
    logger.info("Load test is starting")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when a test is ending"""
    logger.info("Load test is ending")

    # Close system stats writer
    stats_writer.close()

    # Generate summary statistics
    if environment.stats.total.num_requests > 0:
        logger.info("\nTest Summary:")
        logger.info(f"Total Requests: {environment.stats.total.num_requests}")
        logger.info(f"Failed Requests: {environment.stats.total.num_failures}")
        logger.info(f"Average Response Time: {environment.stats.total.avg_response_time:.2f}ms")
        logger.info(f"Median Response Time: {environment.stats.total.median_response_time:.2f}ms")
        logger.info(f"95th Percentile: {environment.stats.total.get_response_time_percentile(0.95):.2f}ms")
        logger.info(f"Requests/s: {environment.stats.total.current_rps:.2f}")


if __name__ == "__main__":
    # Create test_files directory if it doesn't exist
    TEST_FILES_DIR.mkdir(parents=True, exist_ok=True)
