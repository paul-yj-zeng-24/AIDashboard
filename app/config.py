"""
config.py: every setting, loaded once from the .env file.

Why a separate file: secrets (API keys) must never be written into code that
might end up on GitHub. They live in .env (which .gitignore excludes), and
every other module reads them from here instead of touching .env itself.

Each setting has a sensible default, so only the three LLM_* values are
required to get started.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Finds the .env file (searching upward from this file's folder, so it finds
# the project's .env wherever you start the server from) and puts each
# KEY=value line into the process's environment variables, so os.getenv()
# can see them. Variables already set in your shell take precedence.
load_dotenv()

# --- Model provider ----------------------------------------------------------
# The three things any OpenAI-compatible provider needs:
LLM_API_KEY = os.getenv("LLM_API_KEY")    # proves who you are / who pays
LLM_BASE_URL = os.getenv("LLM_BASE_URL")  # which provider's server to call
LLM_MODEL_ID = os.getenv("LLM_MODEL_ID")  # which model on that server
# A cheaper model for bulk work later (inbox triage). `or` falls back to the
# main model when the variable is missing OR empty.
LLM_FAST_MODEL_ID = os.getenv("LLM_FAST_MODEL_ID") or LLM_MODEL_ID

# --- Where things are stored ---------------------------------------------------
# The project folder = two levels up from this file (app/config.py -> project).
PROJECT_DIR = Path(__file__).resolve().parent.parent
# data/ holds everything personal (database, profile). It is git-ignored.
# Tests point DATA_DIR at a temporary folder so they never touch your real data.
DATA_DIR = Path(os.getenv("DATA_DIR", PROJECT_DIR / "data"))
DB_PATH = DATA_DIR / "app.db"
PROFILE_PATH = DATA_DIR / "profile.md"

# --- About you ------------------------------------------------------------------
HOME_NAME = os.getenv("HOME_NAME", "Berkeley, CA")
HOME_LATITUDE = float(os.getenv("HOME_LATITUDE", "37.8716"))
HOME_LONGITUDE = float(os.getenv("HOME_LONGITUDE", "-122.2727"))
TIMEZONE = os.getenv("TIMEZONE", "America/Los_Angeles")
TEMPERATURE_UNIT = os.getenv("TEMPERATURE_UNIT", "fahrenheit")  # or "celsius"

# --- Agent limits ---------------------------------------------------------------
# Stop a turn after this many model calls (a model stuck asking for tools
# would otherwise loop forever and keep spending money).
MAX_STEPS = int(os.getenv("MAX_STEPS", "5"))
# Stop a turn once it has used this many tokens in total (input + output),
# when the provider reports token counts.
RUN_TOKEN_BUDGET = int(os.getenv("RUN_TOKEN_BUDGET", "60000"))
# How many past messages of a conversation are sent to the model each turn.
# Older ones stay in the database but aren't sent (a running summary of them
# is a later improvement).
HISTORY_LIMIT = int(os.getenv("HISTORY_LIMIT", "40"))
