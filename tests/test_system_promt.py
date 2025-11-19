# To run this code you need to install the following dependencies:
# pip install google-genai python-dotenv

import base64
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
project_root = Path(__file__).parent.parent
load_dotenv(project_root / '.env')

# Add project root to path
sys.path.insert(0, str(project_root))

from google import genai
from google.genai import types
from app.services.prompt_builder import get_system_prompt


def generate():
    client = genai.Client(
        api_key=os.environ.get("GEMINI_API_KEY"),
    )

    # Build system prompt from base_system.json + network context
    # include_full_context=False: Uses quick_reference only (saves tokens)
    # include_full_context=True: Includes full network JSON docs
    system_prompt = get_system_prompt(include_full_context=True,  format='text')
    
    print(f"[INFO] System prompt loaded: {len(system_prompt)} characters\n")
    print("=" * 80 + "\n")
    print(system_prompt)
    Path("result/system_prompt_full.txt").write_text(system_prompt, encoding='utf-8')

if __name__ == "__main__":
    generate()
