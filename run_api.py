import os

import uvicorn
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

if __name__ == "__main__":
    # Get port from environment variable or use default
    port = int(os.getenv("PORT", 9192))

    # Run the FastAPI app using uvicorn
    uvicorn.run(
        "mxtoai.api:app",
        host="0.0.0.0",
        port=port,
        reload=True,  # Enable auto-reload for development
    )
