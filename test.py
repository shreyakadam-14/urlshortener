import os
from dotenv import load_dotenv
from supabase import create_client

# Load environment variables
load_dotenv()

# Debug: Print the variables to verify they're loading
print("URL:", os.getenv("SUPABASE_URL"))
print("KEY:", os.getenv("SUPABASE_KEY")[:10] + "...")  # Only show first 10 chars of key

# Create client
try:
    client = create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_KEY")
    )
    print("Connection successful!", client)
except Exception as e:
    print("Connection failed:", str(e))