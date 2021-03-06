# -*- coding: utf-8 -*-
# Maestro Music Manager  -  https://github.com/maestromusic/maestro
# Copyright (C) 2009-2015 Martin Altmayer, Michael Helmling
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

"""Module to manage the database tables used by Maestro."""

from sqlalchemy import *
from . import prefix, FlexiDateType, engine
from ..core import domains as domainsModule, flags as flagsModule, tags as tagsModule

metadata = MetaData(engine)
tables = metadata.tables # mapping keys to sqlalchemy.Table objects


domains = Table(prefix+'domains', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String(domainsModule.MAX_NAME_LENGTH), unique=True),
    mysql_engine='InnoDB'
)

elements = Table(prefix+'elements', metadata,
    Column('id', Integer, primary_key=True),
    Column('domain', Integer, ForeignKey(prefix+'domains.id'), nullable=False),
    Column('file', Boolean, nullable=False),
    Column('type', SmallInteger, nullable=False),
    Column('elements', Integer, nullable=False),
    mysql_engine='InnoDB'
)

contents = Table(prefix+'contents', metadata,
    Column('container_id', Integer, ForeignKey(prefix+'elements.id', ondelete='CASCADE'), primary_key=True),
    Column('position', Integer, primary_key=True),
    Column('element_id', Integer, ForeignKey(prefix+'elements.id', ondelete='CASCADE'),
           nullable=False, index=True),
    mysql_engine='InnoDB'
)

files = Table(prefix+'files', metadata,
    Column('element_id', Integer, ForeignKey(prefix+'elements.id', ondelete='CASCADE'), primary_key=True),
    Column('url', String(500), nullable=False),
        Index(prefix+"files_url_idx", text("url(200)")),  # length must be specified, or MySQL will complain
    Column('hash', String(63), index=True),
    Column('verified', Float, default=0.0, nullable=False),
    Column('length', Integer, nullable=False),
    mysql_engine='InnoDB'
)

tagids = Table(prefix+'tagids', metadata,
    Column('id', Integer, primary_key=True),
    Column('tagname', String(tagsModule.MAX_NAME_LENGTH), nullable=False, index=True, unique=True),
    Column('tagtype', Enum('varchar', 'date', 'text'), server_default='varchar', nullable=False),
    Column('title', String(tagsModule.MAX_NAME_LENGTH)),
    Column('icon', String(255)),
    Column('private', Boolean, nullable=False),
    Column('sort', SmallInteger, nullable=False),
    mysql_engine='InnoDB'
)

tags = Table(prefix+'tags', metadata,
    Column('element_id', Integer, ForeignKey(prefix+'elements.id', ondelete='CASCADE'),
           nullable=False, index=True),
    Column('tag_id', Integer, ForeignKey(prefix+'tagids.id', ondelete='CASCADE'), nullable=False),
    Column('value_id', Integer, nullable=False),
    Index(prefix+'tags_tag_value_idx', "tag_id", "value_id"),
    mysql_engine='InnoDB'
)

values_varchar = Table(prefix+'values_varchar', metadata,
    Column('id', Integer, primary_key=True),
    Column('tag_id', Integer, ForeignKey(prefix+'tagids.id', ondelete='CASCADE'), nullable=False),
    Column('value', String(tagsModule.TAG_VARCHAR_LENGTH), nullable=False),
    Column('sort_value', String(tagsModule.TAG_VARCHAR_LENGTH)),
    Column('search_value', String(tagsModule.TAG_VARCHAR_LENGTH)),
    Column('hide', Boolean, nullable=False, server_default='0'),
    Index(prefix+'values_varchar_idx', "tag_id", "value"),
    mysql_engine='InnoDB'
)

values_text = Table(prefix+'values_text', metadata,
    Column('id', Integer, primary_key=True),
    Column('tag_id', Integer, ForeignKey(prefix+'tagids.id', ondelete='CASCADE'), nullable=False),
    Column('value', Text, nullable=False),
    Index(prefix+'values_text_idx', "tag_id", text("value(200)")),
    mysql_engine='InnoDB'
)
   
values_date = Table(prefix+'values_date', metadata,
    Column('id', Integer, primary_key=True),
    Column('tag_id', Integer, ForeignKey(prefix+'tagids.id', ondelete='CASCADE'), nullable=False),
    Column('value', FlexiDateType, nullable=False),
    Index(prefix+'values_date_idx', "tag_id", "value"),
    mysql_engine='InnoDB'
)
   
flag_names = Table(prefix+'flag_names', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String(flagsModule.MAX_NAME_LENGTH), nullable=False, unique=True),
    Column('icon', String(255)),
    mysql_engine='InnoDB'
)

flags = Table(prefix+'flags', metadata,
    Column('element_id', Integer, ForeignKey(prefix+'elements.id', ondelete='CASCADE'), nullable=False),
    Column('flag_id', Integer, ForeignKey(prefix+'flag_names.id', ondelete='CASCADE'), nullable=False),
    Index(prefix+'flags_idx', "element_id", "flag_id", unique=True),
    mysql_engine='InnoDB'
)

newfiles = Table(prefix+'newfiles', metadata,
    Column('url', String(500), nullable=False),
        Index(prefix+"newfiles_url_idx", text("url(200)")),# length must be specified, or MySQL will complain
    Column('hash', String(63), index=True),
    Column('verified', Float, default=0.0, nullable=False),
    mysql_engine='InnoDB'
)

stickers = Table(prefix+'stickers', metadata,
    Column('element_id', Integer, ForeignKey(prefix+'elements.id', ondelete='CASCADE'), nullable=False),
    Column('type', String(255), nullable=False),
    Column('sort', SmallInteger, nullable=False),
    Column('data', Text, nullable=False),
    Index(prefix+'stickers_idx', "element_id", "type", "sort"),
    mysql_engine='InnoDB'
)
