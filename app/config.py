"""
config.py — settings, loaded once from the .env file.

Why a separate file: secrets (API keys) must never be written into code that
might end up on GitHub. They live in .env (which .gitignore excludes), and
every other module reads them from here instead of touching .env itself.
"""
import os

from dotenv import load_dotenv

# Reads the .env file in the current directory and puts each KEY=value line
# into the process's environment variables, so os.getenv() can see them.
load_dotenv()

# The three things any OpenAI-compatible provider needs:
LLM_API_KEY = os.getenv("LLM_API_KEY")    # proves who you are / who pays
LLM_BASE_URL = os.getenv("LLM_BASE_URL")  # which provider's server to call
LLM_MODEL_ID = os.getenv("LLM_MODEL_ID")  # which model on that server
