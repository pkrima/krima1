from sqlalchemy import inspect

import models
from db import Base, engine

EXPECTED_TABLES = {"users", "reports", "projects"}


def initialize_database():
    Base.metadata.create_all(bind=engine)
    existing_tables = set(inspect(engine).get_table_names())
    missing_tables = EXPECTED_TABLES - existing_tables
    if missing_tables:
        raise RuntimeError(
            "Database initialization did not create required tables: "
            + ", ".join(sorted(missing_tables))
        )

    database_type = engine.dialect.name
    print(f"Database initialized ({database_type}); tables ready: {', '.join(sorted(EXPECTED_TABLES))}.")


if __name__ == "__main__":
    initialize_database()
