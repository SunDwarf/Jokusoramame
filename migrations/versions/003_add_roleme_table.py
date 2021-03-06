"""
Autogenerated migration file.

Revision: 3
Message: Add roleme table.
"""
from asyncqlio.orm.ddl.ddlsession import DDLSession

revision = "3"
message = "Add role table."


async def upgrade(session: DDLSession):
    """
    Performs an upgrade. Put your upgrading SQL here.
    """
    await session.execute("""
    CREATE TABLE roleme_role (
        id BIGINT PRIMARY KEY,
        guild_id BIGINT NOT NULL,
        self_assignable BOOLEAN DEFAULT true
    );
    CREATE INDEX roleme_role_gid_idx ON roleme_role (guild_id);
    """)


async def downgrade(session: DDLSession):
    """
    Performs a downgrade. Put your downgrading SQL here.
    """
    await session.execute("""
    DROP TABLE roleme_role;
    """)
