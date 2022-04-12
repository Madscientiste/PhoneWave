from mongoengine import *

from .role import Role


class Guild(Document):
    guild_id = LongField(required=True, primary_key=True)
    prefix = StringField()
    roles = EmbeddedDocumentListField(Role)
