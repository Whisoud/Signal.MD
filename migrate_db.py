import os
import sys
import json
from supabase import create_client, Client

# Import the new logic from our scraper
from scraper import generate_tags, get_dynamic_category

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Missing Supabase credentials.")
    sys.exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def migrate():
    print("Fetching all existing data from Supabase for migration...")
    all_data = []
    
    # Simple pagination to get all rows
    page = 0
    size = 500
    while True:
        res = supabase.table("signals").select("*").range(page*size, (page+1)*size - 1).execute()
        if not res.data:
            break
        all_data.extend(res.data)
        page += 1
        
    print(f"Fetched {len(all_data)} records. Starting migration...")
    
    updates = []
    for item in all_data:
        title = item.get("title", "")
        summary = item.get("summary", "")
        source = item.get("source", "")
        url = item.get("url")
        
        if not url:
            continue
            
        # Recalculate using the new weighted logic
        new_tags = generate_tags(title, summary, "")
        new_category = get_dynamic_category(new_tags, source)
        
        # Prepare for bulk upsert
        updated_item = item.copy()
        updated_item["tags"] = new_tags
        updated_item["category"] = new_category
        updates.append(updated_item)
        
    print(f"Prepared {len(updates)} records for update.")
    
    # Bulk Upsert
    batch_size = 50
    for i in range(0, len(updates), batch_size):
        batch = updates[i:i+batch_size]
        try:
            supabase.table("signals").upsert(batch, on_conflict="url").execute()
            print(f"  -> Migrated batch {i//batch_size + 1}")
        except Exception as e:
            print(f"Error updating batch: {e}")
            
    print("Migration complete!")

if __name__ == "__main__":
    migrate()
