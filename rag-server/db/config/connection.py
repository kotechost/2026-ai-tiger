import os

DB_HOST     = os.getenv("DB_HOST",     "192.168.0.101")
DB_PORT     = int(os.getenv("DB_PORT", "5432"))
DB_NAME     = os.getenv("DB_NAME",     "bible")
DB_SCHEMA   = os.getenv("DB_SCHEMA",   "bible_service")
DB_USER     = os.getenv("DB_USER",     "solihost")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
