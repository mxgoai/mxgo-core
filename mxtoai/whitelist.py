import os

from supabase import Client, create_client

from mxtoai._logging import get_logger

logger = get_logger(__name__)

# Initialize Supabase client
# supabase: Optional[Client] = None # Removed global variable


def get_supabase_client() -> Client:  # Renamed and changed to return client
    """Initialize and return Supabase client."""
    # global supabase # Removed global keyword
    # if supabase is None: # Removed check for global
    try:
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if not supabase_url or not supabase_key:
            msg = "Supabase URL and service role key must be set in environment variables"
            raise ValueError(msg)

        client = create_client(  # Create local client
            supabase_url=supabase_url,
            supabase_key=supabase_key,
        )
        logger.info("Supabase client initialized successfully")
        return client  # Return the client
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client: {e}")
        raise


async def is_email_whitelisted(email: str) -> tuple[bool, bool]:
    """
    Check if an email is whitelisted and verified in the database

    Args:
        email: The email address to check

    Returns:
        Tuple[bool, bool]: (exists_in_whitelist, is_verified)

    """
    try:
        # if not supabase: # Removed check for global
        #     init_supabase() # Removed call to init_supabase that used global
        supabase_client = get_supabase_client()  # Get client directly

        # Query the whitelist table for the email
        response = supabase_client.table("whitelisted_emails").select("*").eq("email", email).execute()

        # Check if email exists and is verified
        if hasattr(response, "data") and len(response.data) > 0:
            is_verified = response.data[0].get("verified", False)
            logger.info(f"Email whitelist check for {email}: exists=True, verified={is_verified}")
            return True, is_verified
        logger.info(f"Email whitelist check for {email}: exists=False, verified=False")

    except Exception as e:
        logger.error(f"Error checking whitelist status for {email}: {e}")
        return False, False
    else:
        return False, False


def get_whitelist_signup_url() -> str:
    """Get the URL where users can sign up to be whitelisted"""
    return os.getenv("WHITELIST_SIGNUP_URL", "https://mxtoai.com/whitelist-signup")
