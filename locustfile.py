from locust import HttpUser, task, between, events
import random
import json
import os
import psutil
from typing import Dict, List
import csv
from datetime import datetime
import logging
import glob

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("load_test")

def get_random_test_files(num_files: int = 2) -> List[str]:
    """Get random PDF files from test_files directory"""
    pdf_files = glob.glob("test_files/*.pdf")
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
        "files": []
    },
    {
        "subject": "Zero-Knowledge Proofs in Blockchain Privacy",
        "textContent": """I need a detailed explanation of how zero-knowledge proofs work in blockchain privacy solutions. 
        Specifically, how do zk-SNARKs enable transaction privacy while maintaining verifiability? Could you explain the 
        mathematical principles behind zero-knowledge proofs, including the concepts of completeness, soundness, and 
        zero-knowledge? Also, how do recursive SNARKs work in scaling solutions, and what are the trade-offs between 
        different types of zero-knowledge proof systems (SNARKs vs STARKs)? Please include real-world applications in 
        privacy-focused blockchain platforms.""",
        "files": []
    }
]

# Test scenarios with weights
EMAIL_SCENARIOS = [
    {
        "weight": 50,  # 70% of requests will use this scenario
        "data": {
            "from_email": "test@example.com",
            "to": random.choice(["summarise@mxtoai.com", "eli5@mxtoai.com"]),
            **random.choice(superficial_presets)  # Use random complex topic
        }
    },
    {
        "weight": 20,  # 20% of requests
        "data": {
            "from_email": "test@example.com",
            "to": "translate@mxtoai.com",
            **random.choice(superficial_presets)
        }
    },
    {
        "weight": 30,  # 10% of requests
        "data": {
            "from_email": "test@example.com",
            "to": "ask@mxtoai.com",
            "subject": "Please find attachments",
            "textContent": random.choice(
                ["Please analyse and summarise each of the attached documents", "Please analyse and summarise each of the attached documents", "Please analyse and summarise each of the attached documents",
                 "Please analyse and leave detailed feedback about the formatting of each of the attached documents"]),
            "files": get_random_test_files(2)  # Two random PDF files
        }
    }
]

# System resource monitoring
def get_system_stats() -> Dict:
    """Get current system resource usage"""
    process = psutil.Process(os.getpid())
    return {
        "cpu_percent": process.cpu_percent(),
        "memory_percent": process.memory_percent(),
        "num_threads": process.num_threads(),
        "connections": len(process.net_connections())
    }

# CSV writer for system stats
class SystemStatsWriter:
    def __init__(self, filename: str):
        self.filename = filename
        self.file = open(filename, 'w', newline='')
        self.writer = csv.writer(self.file)
        self.writer.writerow(['timestamp', 'cpu_percent', 'memory_percent', 'num_threads', 'connections'])
    
    def write_stats(self, stats: Dict):
        self.writer.writerow([
            datetime.now().isoformat(),
            stats['cpu_percent'],
            stats['memory_percent'],
            stats['num_threads'],
            stats['connections']
        ])
    
    def close(self):
        self.file.close()

# Initialize system stats writer
stats_writer = SystemStatsWriter('system_stats.csv')

class EmailProcessingUser(HttpUser):
    wait_time = between(0.5, 1.5)  # Random wait between requests
    
    def on_start(self):
        """Setup before tests start"""
        # Verify test files exist
        for scenario in EMAIL_SCENARIOS:
            for file_path in scenario["data"].get("files", []):
                if not os.path.exists(file_path):
                    logger.warning(f"Test file not found: {file_path}")

    @task
    def process_email(self):
        """Send email processing request based on weighted scenarios"""
        # Select scenario based on weights
        scenario = random.choices(
            EMAIL_SCENARIOS, 
            weights=[s["weight"] for s in EMAIL_SCENARIOS],
            k=1
        )[0]
        
        # For the third scenario, get fresh random files each time
        if scenario["data"]["to"] == "full-analysis@mxtoai.com":
            scenario["data"]["files"] = get_random_test_files(2)
        
        # Prepare the request data
        data = scenario["data"].copy()
        files = []
        
        # Add files if present in scenario
        for file_path in data.pop("files", []):
            try:
                files.append(
                    ("files", (
                        os.path.basename(file_path),
                        open(file_path, "rb"),
                        "application/pdf"
                    ))
                )
            except FileNotFoundError:
                logger.error(f"File not found: {file_path}")
                continue
        
        try:
            # Send the request
            with self.client.post(
                "/process-email",
                data=data,
                files=files,
                catch_response=True
            ) as response:
                # Record system stats
                stats_writer.write_stats(get_system_stats())
                
                # Validate response
                if response.status_code == 200:
                    response_data = response.json()
                    if response_data.get("message") == "Email processed successfully":
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
    os.makedirs("test_files", exist_ok=True)