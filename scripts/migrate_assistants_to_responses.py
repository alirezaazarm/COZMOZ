"""One-time MongoDB migration from Assistants API state to Responses API state.

Run once, after deploying the code, from the repository root:
    python scripts/migrate_assistants_to_responses.py

It does not delete OpenAI files or vector stores.  Old Assistant and Thread
objects cannot be converted to Responses objects, so users start their next
turn as a new Responses conversation while their local message history remains.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.database import CLIENTS_COLLECTION, USERS_COLLECTION, db

DEFAULT_AI_CONFIG = {
    "model": "gpt-4.1-mini",
    "instructions": "",
    "temperature": 1.0,
    "top_p": 1.0,
}


def main():
    clients = db[CLIENTS_COLLECTION].update_many(
        {"ai": {"$exists": False}}, {"$set": {"ai": DEFAULT_AI_CONFIG}}
    )
    users = db[USERS_COLLECTION].update_many(
        {}, {"$set": {"response_id": None}, "$unset": {"thread_id": ""}}
    )
    print(f"Initialized Responses settings for {clients.modified_count} clients.")
    print(f"Cleared legacy Assistant thread state for {users.modified_count} users.")


if __name__ == "__main__":
    main()
