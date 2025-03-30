import os

# List of email addresses for which we skip sending email replies
# Useful for testing and development environments
SKIP_EMAIL_DELIVERY = [
    "test@example.com",
]
# Ensure attachments directory exists with absolute path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ATTACHMENTS_DIR = os.path.abspath(os.path.join(parent_dir, "attachments"))
os.makedirs(ATTACHMENTS_DIR, exist_ok=True)

