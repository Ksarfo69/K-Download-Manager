from abc import abstractmethod
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session


class DBService:
    @abstractmethod
    def insert(self, instance):
        ...

    @abstractmethod
    def get(self, feature, condition):
        ...

    @abstractmethod
    def get_all(self, feature, condition, limit: int = None):
        ...

    @abstractmethod
    def delete(self, instance):
        ...

    @abstractmethod
    def update(self, table, values: dict):
        ...


class SQLAlchemyDBService(DBService):
    def __init__(self, engine):
        self.__Session = sessionmaker(bind=engine)

    @contextmanager
    def get_session(self) -> Session:
        session = None
        try:
            session = self.__Session()
            yield session
        finally:
            if session:
                session.close()

    async def insert(self, instance):
        with self.get_session() as s:
            if instance:
                s.add(instance)

            s.commit()
            s.refresh(instance)

    async def get(self, feature, condition):
        with self.get_session() as s:
            res = s.query(feature).filter(condition).first()

            return res

    async def get_all(self, feature, condition = None, order_by = None, offset: int = None, limit: int = None):
        res = []
        with self.get_session() as s:
            query = s.query(feature)

            if condition is not None:
                query = query.filter(condition)

            if order_by is not None:
                query = query.order_by(order_by)

            if offset is not None:
                query = query.offset(offset)

            if limit is not None:
                query = query.limit(limit)

            try:
                res = query.all()
            except:
                ...

            return res

    async def delete(self, instance):
        with self.get_session() as s:
            s.delete(instance)
            s.commit()

    async def update(self, table, values: dict):
        with self.get_session() as s:
            s.query(table).update(values)

            s.commit()


engine = create_engine('sqlite:///kdm.db')
sadbs: SQLAlchemyDBService = SQLAlchemyDBService(engine=engine)
