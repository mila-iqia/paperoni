from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql.sqltypes import NullType

Base = declarative_base()
metadata = Base.metadata


class Affiliation(Base):
    __tablename__ = "affiliation"

    name = Column(Text, nullable=False)
    affiliation_id = Column(Integer, primary_key=True)

    paper_author = relationship(
        "PaperAuthor",
        secondary="paper_author_affiliation",
        back_populates="affiliation",
    )
    affiliation_alias = relationship(
        "AffiliationAlias", back_populates="affiliation"
    )
    author_affiliation = relationship(
        "AuthorAffiliation", back_populates="affiliation"
    )


class Author(Base):
    __tablename__ = "author"

    author_name = Column(Text, nullable=False)
    author_id = Column(Integer, primary_key=True)

    author_affiliation = relationship(
        "AuthorAffiliation", back_populates="author"
    )
    paper_author = relationship("PaperAuthor", back_populates="author")


class Paper(Base):
    __tablename__ = "paper"

    paper_id = Column(Integer, primary_key=True)
    title = Column(Text)
    abstract = Column(Text)
    citation_count = Column(Integer)

    topic = relationship(
        "Topic", secondary="paper_topic", back_populates="paper"
    )
    release = relationship(
        "Release", secondary="paper_release", back_populates="paper"
    )
    paper_author = relationship("PaperAuthor", back_populates="paper")
    paper_flag = relationship("PaperFlag", back_populates="paper")


t_sqlite_sequence = Table(
    "sqlite_sequence",
    metadata,
    Column("name", NullType),
    Column("seq", NullType),
)


class Topic(Base):
    __tablename__ = "topic"

    topic = Column(Text, nullable=False)
    topic_id = Column(Integer, primary_key=True)
    parent = Column(ForeignKey("topic.topic_id"))

    paper = relationship(
        "Paper", secondary="paper_topic", back_populates="topic"
    )
    topic_ = relationship(
        "Topic", remote_side=[topic_id], back_populates="topic__reverse"
    )
    topic__reverse = relationship(
        "Topic", remote_side=[parent], back_populates="topic_"
    )


class Venue(Base):
    __tablename__ = "venue"

    venue_name = Column(Text, nullable=False)
    venue_id = Column(Integer, primary_key=True)
    venue_type = Column(Text)

    release = relationship("Release", back_populates="venue")


class AffiliationAlias(Base):
    __tablename__ = "affiliation_alias"

    alias = Column(Text, primary_key=True, nullable=False)
    affiliation_id = Column(
        ForeignKey("affiliation.affiliation_id"), primary_key=True
    )

    affiliation = relationship(
        "Affiliation", back_populates="affiliation_alias"
    )


class AuthorAffiliation(Base):
    __tablename__ = "author_affiliation"

    role = Column(Text, primary_key=True, nullable=False)
    start_date = Column(Integer, primary_key=True, nullable=False)
    author_id = Column(ForeignKey("author.author_id"), primary_key=True)
    affiliation_id = Column(
        ForeignKey("affiliation.affiliation_id"), primary_key=True
    )
    end_date = Column(Integer)

    affiliation = relationship(
        "Affiliation", back_populates="author_affiliation"
    )
    author = relationship("Author", back_populates="author_affiliation")


t_author_alias = Table(
    "author_alias",
    metadata,
    Column("author_id", ForeignKey("author.author_id")),
    Column("alias", Text, nullable=False),
    UniqueConstraint("author_id", "alias"),
)


t_author_link = Table(
    "author_link",
    metadata,
    Column("author_id", ForeignKey("author.author_id")),
    Column("link_type", Text, nullable=False),
    Column("link", Text, nullable=False),
    UniqueConstraint("author_id", "link_type", "link"),
)


class PaperAuthor(Base):
    __tablename__ = "paper_author"

    author_position = Column(Integer, nullable=False)
    paper_id = Column(ForeignKey("paper.paper_id"), primary_key=True)
    author_id = Column(ForeignKey("author.author_id"), primary_key=True)

    affiliation = relationship(
        "Affiliation",
        secondary="paper_author_affiliation",
        back_populates="paper_author",
    )
    author = relationship("Author", back_populates="paper_author")
    paper = relationship("Paper", back_populates="paper_author")


class PaperFlag(Base):
    __tablename__ = "paper_flag"
    __table_args__ = (CheckConstraint("flag in (0, 1)"),)

    flag_name = Column(Text, primary_key=True, nullable=False)
    flag = Column(Integer, nullable=False, server_default=text("0"))
    paper_id = Column(ForeignKey("paper.paper_id"), primary_key=True)

    paper = relationship("Paper", back_populates="paper_flag")


t_paper_link = Table(
    "paper_link",
    metadata,
    Column("paper_id", ForeignKey("paper.paper_id")),
    Column("link_type", Text, nullable=False),
    Column("link", Text, nullable=False),
    UniqueConstraint("paper_id", "link_type", "link"),
)


t_paper_topic = Table(
    "paper_topic",
    metadata,
    Column("paper_id", ForeignKey("paper.paper_id"), primary_key=True),
    Column("topic_id", ForeignKey("topic.topic_id"), primary_key=True),
)


class Release(Base):
    __tablename__ = "release"
    __table_args__ = (UniqueConstraint("venue_id", "volume"),)

    date_precision = Column(Integer, nullable=False)
    volume = Column(Text, nullable=False)
    publisher = Column(Text, nullable=False)
    release_id = Column(Integer, primary_key=True)
    venue_id = Column(ForeignKey("venue.venue_id"))
    release_date = Column(Integer)

    paper = relationship(
        "Paper", secondary="paper_release", back_populates="release"
    )
    venue = relationship("Venue", back_populates="release")


t_paper_author_affiliation = Table(
    "paper_author_affiliation",
    metadata,
    Column("paper_id", Integer, primary_key=True),
    Column("author_id", Integer, primary_key=True),
    Column(
        "affiliation_id",
        ForeignKey("affiliation.affiliation_id"),
        primary_key=True,
    ),
    ForeignKeyConstraint(
        ["paper_id", "author_id"],
        ["paper_author.paper_id", "paper_author.author_id"],
        ondelete="CASCADE",
    ),
)


t_paper_release = Table(
    "paper_release",
    metadata,
    Column("paper_id", ForeignKey("paper.paper_id"), primary_key=True),
    Column("release_id", ForeignKey("release.release_id"), primary_key=True),
)
