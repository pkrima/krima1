import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
tidb_host = os.environ.get("TIDB_HOST")
connect_args = {}

if DATABASE_URL:
    database_url = DATABASE_URL
    parsed_url = make_url(database_url)
    if parsed_url.drivername.startswith("mysql"):
        ca_setting = os.environ.get("TIDB_CA_PATH")
        if ca_setting:
            ca_path = Path(ca_setting)
            if not ca_path.is_file():
                raise RuntimeError(f"Database CA certificate not found: {ca_path}")
            connect_args["ssl"] = {"ca": str(ca_path)}
        elif parsed_url.host and parsed_url.host.endswith(".tidbcloud.com"):
            raise RuntimeError("Set TIDB_CA_PATH to the TiDB Cloud CA certificate.")
elif tidb_host:
    required_settings = ("TIDB_USERNAME", "TIDB_PASSWORD", "TIDB_CA_PATH")
    missing_settings = [name for name in required_settings if not os.environ.get(name)]
    if missing_settings:
        raise RuntimeError(
            "TiDB configuration is incomplete. Set: " + ", ".join(missing_settings)
        )

    ca_path = Path(os.environ["TIDB_CA_PATH"])
    if not ca_path.is_file():
        raise RuntimeError(f"TiDB CA certificate not found: {ca_path}")

    database_url = URL.create(
        "mysql+pymysql",
        username=os.environ["TIDB_USERNAME"],
        password=os.environ["TIDB_PASSWORD"],
        host=tidb_host,
        port=int(os.environ.get("TIDB_PORT", "4000")),
        database=os.environ.get("TIDB_DATABASE", "test"),
    )
    connect_args["ssl"] = {"ca": str(ca_path)}
else:
    partial_tidb_settings = [
        name
        for name in ("TIDB_USERNAME", "TIDB_PASSWORD", "TIDB_CA_PATH")
        if os.environ.get(name)
    ]
    if partial_tidb_settings:
        raise RuntimeError(
            "TiDB settings are present but TIDB_HOST is missing. Set TIDB_HOST "
            "or clear the TiDB settings to use SQLite."
        )
    database_url = "sqlite:///career_copilot.db"
    connect_args["check_same_thread"] = False

engine = create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()
