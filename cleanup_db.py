import os
import sys
from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Missing Supabase credentials.")
    sys.exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

try:
    print("Deleting 36kr data...")
    res_36kr = supabase.table("signals").delete().eq("source", "36氪").execute()
    print(f"Deleted {len(res_36kr.data)} records from 36氪.")

    print("Deleting FDA MedDevice data...")
    res_fda = supabase.table("signals").delete().eq("source", "FDA MedDevice").execute()
    print(f"Deleted {len(res_fda.data)} records from FDA MedDevice.")

    print("Cleanup complete.")
except Exception as e:
    print(f"Error during deletion: {e}")
