# MXTOAI Email Processing System

A robust email processing system that can handle, analyze, and respond to emails with advanced attachment processing capabilities.

## Features

- **Email Summarization**: Generate concise, structured summaries of email content including key points and action items.
- **Smart Reply Generation**: Create context-aware email replies based on the email's purpose and content.
- **Advanced Attachment Processing**: Analyze various types of attachments including:
  - **Documents**: PDF, DOCX, XLSX, PPTX, TXT, HTML
  - **Images**: JPG, PNG, GIF with Azure Vision-powered image captioning
  - **Media**: Various media file types with basic metadata extraction
- **Deep Research**: Optional integration with research APIs to provide deeper insights on email topics.
- **Multiple Processing Modes**: Process emails in different modes depending on your needs:
  - `summary`: Just generate a summary
  - `reply`: Just generate a reply
  - `research`: Perform research based on the email content
  - `full`: Complete processing (summary, reply, and research)
- **Rich Text Formatting**: Supports both HTML and plain text email responses with proper formatting
- **Attachment Analysis**: Provides detailed summaries of attachment contents in the email response
- **Error Resilience**: Graceful handling of processing errors with fallback responses
- **Asynchronous Processing**: Uses Dramatiq for reliable background task processing
- **Scalable Architecture**: Multiple workers can process emails concurrently

## Directory Structure

```
mxtoai/
├── agents/                 # Agent implementations for different tasks
│   └── email_agent.py     # Main email processing agent implementation
├── tools/                 # Individual tool implementations
│   ├── attachment_processing_tool.py  # Attachment handling
│   ├── email_reply_tool.py        # Email reply generation
│   └── deep_research_tool.py      # Research capabilities
├── scripts/              # Utility scripts and helpers
│   ├── visual_qa.py     # Azure Vision integration for images
│   ├── citation_tools.py # Citation and reference handling
│   ├── text_web_browser.py # Web content retrieval
│   └── report_formatter.py  # Email response formatting
├── attachments/         # Temporary storage for attachments
└── ai.py              # AI model configurations and utilities
```

## Architecture

The system uses a message queue architecture with Dramatiq for reliable email processing:

1. **API Layer**: Receives email requests and queues them for processing
2. **Message Queue**: Uses Redis as the message broker
3. **Worker Processes**: Multiple Dramatiq workers process emails concurrently
4. **Error Handling**: Built-in retry mechanism for failed tasks

## Setup and Installation

### Prerequisites

- Python 3.12+
- Redis server (for message queue)
- Azure OpenAI API access
- Azure Vision API access (for image processing)

### Installation

The project uses Poetry for dependency management. Here's how to set it up:

1. First, install Poetry if you haven't already:
```bash
# On macOS/Linux/WSL
curl -sSL https://install.python-poetry.org | python3 -

# On Windows (PowerShell)
(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | py -
```

2. Clone and set up the project:
```bash
# Clone the repository
git clone https://github.com/satwikkansal/mxtoai.git
cd mxtoai

# Install dependencies using Poetry
poetry install

# Activate the virtual environment
poetry shell
```

3. Start RabbitMQ server:
```bash
brew services restart rabbitmq
```

4. Start the API server:
```bash
poetry run python run_api.py
```

5. Start the workers:

Using only single process and couple of threads for local development:

```bash
poetry run dramatiq mxtoai.tasks --processes 1 --threads 2 --watch ./.
```

### Environment Variables

Copy the `.env.example` file to `.env` and update with your specific configuration:

```env
LITELLM_CONFIG_PATH=model.config.toml

# Redis configuration
REDIS_HOST=localhost
REDIS_PORT=6379

# Optional for research functionality
JINA_API_KEY=your-jina-api-key

# For image processing
AZURE_VISION_ENDPOINT=your-azure-vision-endpoint
AZURE_VISION_KEY=your-azure-vision-key

# For web search functionality
SERPAPI_API_KEY=your-serpapi-api-key
```

This project supports load balancing and routing across multiple models, so you can define as many models as you'd like. Copy `model.config.example.toml` to a toml file and update it with your preferred configuration. Update `.env` with the path your toml relative to root.

A sample configuration looks like this:

```toml
[[model]]
model_name = "gpt-4"

[model.litellm_params]
model = "azure/gpt-4"
base_url = "https://your-endpoint.openai.azure.com"
api_key = "your-key"
api_version = "2023-05-15"
weight = 5
```

It is also recommended that you set router configuration. It will be defaulted to the below config if not set.

```toml
[router_config]
routing_strategy = "simple-shuffle"

[[router_config.fallbacks]]
gpt-4 = ["gpt-4-reasoning"]

[router_config.default_litellm_params]
drop_params = true
```

## API Endpoints

### Process Email

```
POST /process-email
```

#### Response Example

```json
{
    "message": "Email received and queued for processing",
    "email_id": "1743315736--3926735152910876943",
    "attachments_saved": 1,
    "status": "processing"
}
```

The email will be processed asynchronously by the workers. You can implement a status check endpoint to monitor the processing status.

## Email Processing Flow

```mermaid
graph TD
    A[Incoming Email] --> B[Email Routing]
    B --> C{Determine Mode}

    C -->|summarize@| D[Summary Mode]
    C -->|reply@| E[Reply Mode]
    C -->|research@| F[Research Mode]
    C -->|ask@| G[Full Mode]

    %% Attachment Processing
    A --> H[Attachment Detection]
    H --> I{File Type}
    I -->|Images| J[Azure Vision Analysis]
    I -->|Documents| K[Document Processing]
    I -->|Other| L[Metadata Extraction]

    J --> M[Generate Captions]
    K --> N[Extract Content]
    L --> O[Basic Info]

    M & N & O --> P[Attachment Summary]

    %% Mode Processing
    D & E & F & G --> Q[Process Request]
    P --> Q

    Q --> R[Format Response]
    R --> S[Generate HTML]
    R --> T[Generate Text]

    %% Error Handling
    Q --> U{Errors?}
    U -->|Yes| V[Fallback Response]
    U -->|No| R

    %% Final Response
    S & T --> W[Final Response]
    V --> W

    %% Styling
    classDef email fill:#f9f,stroke:#333,stroke-width:2px
    classDef process fill:#bbf,stroke:#333,stroke-width:2px
    classDef error fill:#fbb,stroke:#333,stroke-width:2px

    class A,B email
    class D,E,F,G,Q,R process
    class U,V error
```

## Running the API Server

```bash
# Start the FastAPI server
uvicorn api:app --reload
```

## Scheduler Setup & Running

The scheduler runs as a **separate process** from the API server and Dramatiq workers. This ensures clean separation and scalability.

### 1. Ensure Environment Variables

Add these to your `.env` (or set in your environment):

```env
# Database (PostgreSQL) settings
DB_HOST=localhost
DB_PORT=5432
DB_NAME=your_database
DB_USER=your_user
DB_PASSWORD=your_password

# Scheduler settings
SCHEDULER_API_BASE_URL=http://localhost:8000
SCHEDULER_API_TIMEOUT=300
SCHEDULER_MAX_WORKERS=5
```

### 2. Run Database Migration

Make sure your database is up to date:

```bash
poetry run alembic upgrade head
```

### 3. Start All Processes

You need to run **three separate processes**:

```bash
# Terminal 1: API Server
poetry run python run_api.py

# Terminal 2: Dramatiq Workers (multiple processes)
poetry run dramatiq mxtoai.tasks --processes 8 --threads 2 --watch ./

# Terminal 3: Scheduler Process (separate)
poetry run python -m mxtoai.scheduler_runner
```

**How it works:**
- Dramatiq workers handle emails and write scheduled tasks to PostgreSQL
- Scheduler process reads from PostgreSQL and executes tasks by calling the API
- API server processes both regular and scheduled emails

## Advanced Features

### Attachment Processing

The system now supports:
- Automatic content extraction from documents
- Azure Vision-powered image analysis and captioning
- Fallback processing for unsupported file types
- Size-aware content summarization
- Error resilient processing

### Response Formatting

- Rich text formatting with markdown support
- Both HTML and plain text versions
- Automatic signature handling
- Attachment content integration
- Professional formatting with sections and highlights

### Error Handling

- Graceful degradation on processing failures
- Detailed error tracking and reporting
- Fallback responses for partial failures
- Comprehensive error logging

## Load Testing

The project uses Locust for load testing various email processing scenarios.

### Setup & Run

1. Install and setup:
```bash
pip install locust
mkdir -p test_files
# Add 2-3 PDF files to test_files/ directory
```

2. Run tests:
```bash
# Interactive mode (Recommended)
locust --host=http://localhost:8000

# Or headless mode
poetry run locust --host=http://localhost:9192 --users 10 --spawn-rate 2 --run-time 1m --headless
```

### Test Scenarios

- Simple queries (50%): Complex questions to summarise@mxtoai.com
- Translation requests (20%): Technical content to translate@mxtoai.com
- Document analysis (30%): PDF attachments to ask@mxtoai.com

### Results & Monitoring

- Real-time stats in Web UI (http://localhost:8089)
- System metrics in results/system_stats.csv
- HTML report and logs in results/ directory

For detailed configuration, check `locustfile.py`.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## New Scheduler Process

To run the new scheduler process, use the following command:

```bash
poetry run python -m mxtoai.scheduler_runner
```
