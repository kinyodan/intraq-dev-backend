from db.models import Client, SessionLocal

def list_clients():
    db = SessionLocal()
    try:
        return db.query(Client).all()
    finally:
        db.close()
