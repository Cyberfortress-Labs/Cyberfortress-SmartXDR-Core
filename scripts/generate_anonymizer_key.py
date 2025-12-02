# 1. Generate key 1 lần
from app.core.anonymizer import KeyManager


key = KeyManager.generate_key_for_env()
print(f"Add to .env: ANONYMIZER_ENCRYPTION_KEY={key}")