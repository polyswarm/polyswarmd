import logging

from sqlalchemy import create_engine, Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship, scoped_session, sessionmaker
from sqlalchemy.ext.declarative import declarative_base

from polyswarmd.config import db_uri

engine = create_engine(db_uri, convert_unicode=True)
db_session = scoped_session(
    sessionmaker(autocommit=False, autoflush=False, bind=engine))

Base = declarative_base()
Base.query = db_session.query_property()


class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    email = Column(String, index=True, unique=True)

    eth_addresses = relationship(
        'EthAddress', backref='user', cascade='all, delete-orphan')

    def __init__(self, email=None):
        self.email = email

    def __repr__(self):
        return '<User {0}>'.format(self.email)


class EthAddress(Base):
    __tablename__ = 'eth_addresses'
    id = Column(Integer, primary_key=True)
    eth_address = Column(String, index=True)

    user_id = Column(Integer, ForeignKey('users.id'))

    api_keys = relationship(
        'ApiKey', backref='eth_address', cascade='all, delete-orphan')

    def __init__(self, eth_address=None):
        self.eth_address = eth_address

    def __repr__(self):
        return '<EthAddress {0}>'.format(self.eth_address)


class ApiKey(Base):
    __tablename__ = 'api_keys'
    id = Column(Integer, primary_key=True)
    api_key = Column(String, index=True, unique=True)

    eth_address_id = Column(Integer, ForeignKey('eth_addresses.id'))

    def __init__(self, api_key=None):
        self.api_key = api_key

    def __repr__(self):
        return '<ApiKey {0}>'.format(self.api_key)


def init_db():
    Base.metadata.create_all(bind=engine)


def lookup_api_key(api_key):
    try:
        return ApiKey.query.filter(ApiKey.api_key == api_key).first()
    except:
        return None


# For debugging
def add_api_key(email, eth_address, api_key):
    try:
        user_obj = User(email)
        eth_address_obj = EthAddress(eth_address)
        api_key_obj = ApiKey(api_key)

        eth_address_obj.api_keys.append(api_key_obj)
        user_obj.eth_addresses.append(eth_address_obj)

        db_session.add(user_obj)
        db_session.commit()
    except Exception as e:
        logging.error('Error inserting new API key into DB: %s', e)
        db_session.rollback()
