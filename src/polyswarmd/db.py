import logging

from flask import current_app as app
from sqlalchemy import create_engine, Column, ForeignKey, Integer, String, Table
from sqlalchemy.orm import relationship, scoped_session, sessionmaker
from sqlalchemy.ext.declarative import declarative_base

logger = logging.getLogger(__name__)
engine = create_engine(app.config['POLYSWARMD'].db_uri, convert_unicode=True)
db_session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

Base = declarative_base()
Base.query = db_session.query_property()

community_user = Table('community_user', Base.metadata,
                       Column('community_id', Integer, ForeignKey('communities.id')),
                       Column('user_id', Integer, ForeignKey('users.id'))
                       )

community_api_key = Table('community_api_key', Base.metadata,
                          Column('community_id', Integer, ForeignKey('communities.id')),
                          Column('api_key_id', Integer, ForeignKey('api_keys.id'))
                          )


class Community(Base):
    __tablename__ = 'communities'
    id = Column(Integer, primary_key=True)
    name = Column(String, index=True, unique=True)

    users = relationship('User', secondary=community_user, back_populates='communities')
    api_keys = relationship('ApiKey', secondary=community_api_key, back_populates='communities')

    def __init__(self, name=None):
        self.name = name

    def __repr(self):
        return '<Community {0}>'.format(self.name)


class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    email = Column(String, index=True, unique=True)

    communities = relationship('Community', secondary=community_user, back_populates='users')
    api_keys = relationship('ApiKey', backref='user', cascade='all, delete-orphan')

    def __init__(self, email=None, communities=None):
        self.email = email
        self.communities = communities

    def __repr__(self):
        return '<User {0}>'.format(self.email)


class ApiKey(Base):
    __tablename__ = 'api_keys'
    id = Column(Integer, primary_key=True)
    api_key = Column(String, index=True, unique=True)

    communities = relationship('Community', secondary=community_api_key, back_populates='api_keys')
    user_id = Column(Integer, ForeignKey('users.id'))

    def __init__(self, api_key=None, communities=None):
        self.api_key = api_key
        self.communities = communities

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
        api_key_obj = ApiKey(api_key)

        user_obj.api_keys.append(api_key_obj)

        db_session.add(user_obj)
        db_session.commit()
    except Exception:
        logger.exception('Error inserting new API key into DB')
        db_session.rollback()


@app.teardown_appcontext
def teardown_appcontext(exception=None):
    db_session.remove()
