from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, URL


@dataclass
class Session:
    engine: Engine
    connection_id: int
    database: str


sessions: dict[str, Session] = {}


def create_session(engine: Engine, connection_id: int, database: str) -> str:
    session_id = uuid4().hex
    sessions[session_id] = Session(engine=engine, connection_id=connection_id, database=database)
    return session_id


def get_session(session_id: str) -> Session | None:
    return sessions.get(session_id)


def make_engine(username: str, password: str, host: str, port: int, database: str) -> Engine:
    url = URL.create(
        "mysql+pymysql", username=username, password=password, host=host, port=port, database=database
    )
    return create_engine(url, pool_pre_ping=True)
