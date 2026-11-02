from .db import Session


def database():
    with Session() as db:
        yield db
