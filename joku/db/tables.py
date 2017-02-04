from sqlalchemy import Column, BigInteger, Integer, DateTime, func, String, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class User(Base):
    """
    A user object in the database.
    """
    __tablename__ = "user"

    #: The ID of the user.
    #: This is their snowflake ID.
    id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=False,
                unique=True)

    #: The XP points of the user.
    xp = Column(Integer, nullable=False, default=0)

    #: The level of the user.
    #: This is automatically calculated.
    level = Column(Integer, nullable=False, default=1)

    #: The money of the user.
    money = Column(Integer, nullable=False, default=200)

    #: The last modified time of the user.
    last_modified = Column(DateTime(), server_default=func.now())

    #: The inventory for this user.
    inventory = relationship("UserInventoryItem")

    def __repr__(self):
        return "<User id={} xp={} money={}>".format(self.id, self.xp, self.money)

    __str__ = __repr__


class UserInventoryItem(Base):
    """
    Represents an item in a user's inventory.
    """
    __tablename__ = "user_inv_item"

    #: The ID for this inventory item.
    id = Column(Integer, primary_key=True, autoincrement=True)

    #: The user ID for this inventory item.
    user_id = Column(BigInteger, ForeignKey('user.id'))

    #: The item ID for this inventory item.
    #: Used internally.
    item_id = Column(Integer, autoincrement=False, nullable=False)

    #: The count for this inventory item.
    count = Column(Integer, autoincrement=False, nullable=False)


class Setting(Base):
    """
    A setting object in the database.
    """
    __tablename__ = "setting"

    #: The ID of the setting.
    id = Column(Integer, primary_key=True, nullable=False, autoincrement=True)

    #: The name of the setting.
    name = Column(String, nullable=False, unique=False)

    #: The value of the setting.
    value = Column(JSONB, nullable=False)

    #: The guild ID this setting is in.
    guild_id = Column(BigInteger, unique=False, nullable=False)
