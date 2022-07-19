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


class Author(Base):
    __tablename__ = "author"

    name = Column(Text, nullable=False)
    author_id = Column(Integer, primary_key=True)

    author_alias = relationship("AuthorAlias", back_populates="author")
    author_institution = relationship(
        "AuthorInstitution", back_populates="author"
    )
    author_link = relationship("AuthorLink", back_populates="author")
    paper_author = relationship("PaperAuthor", back_populates="author")


class Institution(Base):
    __tablename__ = "institution"
    __table_args__ = (
        CheckConstraint("category in ('unknown', 'academia', 'industry')"),
    )

    name = Column(Text, nullable=False)
    category = Column(Text, nullable=False, server_default=text("'unknown'"))
    institution_id = Column(Integer, primary_key=True)

    paper_author = relationship(
        "PaperAuthor",
        secondary="paper_author_institution",
        back_populates="institution",
    )
    author_institution = relationship(
        "AuthorInstitution", back_populates="institution"
    )
    institution_alias = relationship(
        "InstitutionAlias", back_populates="institution"
    )


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
    paper_link = relationship("PaperLink", back_populates="paper")
    paper_scraper = relationship("PaperScraper", back_populates="paper")


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

    name = Column(Text, nullable=False)
    venue_id = Column(Integer, primary_key=True)
    type = Column(Text)

    release = relationship("Release", back_populates="venue")
    venue_alias = relationship("VenueAlias", back_populates="venue")
    venue_link = relationship("VenueLink", back_populates="venue")


class AuthorAlias(Base):
    __tablename__ = "author_alias"

    alias = Column(Text, primary_key=True, nullable=False)
    author_id = Column(ForeignKey("author.author_id"), primary_key=True)

    author = relationship("Author", back_populates="author_alias")


class AuthorInstitution(Base):
    __tablename__ = "author_institution"

    role = Column(Text, primary_key=True, nullable=False)
    start_date = Column(Integer, primary_key=True, nullable=False)
    author_id = Column(ForeignKey("author.author_id"), primary_key=True)
    institution_id = Column(
        ForeignKey("institution.institution_id"), primary_key=True
    )
    end_date = Column(Integer)

    author = relationship("Author", back_populates="author_institution")
    institution = relationship(
        "Institution", back_populates="author_institution"
    )


class AuthorLink(Base):
    __tablename__ = "author_link"

    type = Column(Text, primary_key=True, nullable=False)
    link = Column(Text, primary_key=True, nullable=False)
    author_id = Column(ForeignKey("author.author_id"), primary_key=True)

    author = relationship("Author", back_populates="author_link")


class InstitutionAlias(Base):
    __tablename__ = "institution_alias"

    alias = Column(Text, primary_key=True, nullable=False)
    institution_id = Column(
        ForeignKey("institution.institution_id"), primary_key=True
    )

    institution = relationship(
        "Institution", back_populates="institution_alias"
    )


class PaperAuthor(Base):
    __tablename__ = "paper_author"

    author_position = Column(Integer, nullable=False)
    paper_id = Column(ForeignKey("paper.paper_id"), primary_key=True)
    author_id = Column(ForeignKey("author.author_id"), primary_key=True)

    institution = relationship(
        "Institution",
        secondary="paper_author_institution",
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


class PaperLink(Base):
    __tablename__ = "paper_link"

    type = Column(Text, primary_key=True, nullable=False)
    link = Column(Text, primary_key=True, nullable=False)
    paper_id = Column(ForeignKey("paper.paper_id"), primary_key=True)

    paper = relationship("Paper", back_populates="paper_link")


class PaperScraper(Base):
    __tablename__ = "paper_scraper"

    paper_id = Column(ForeignKey("paper.paper_id"), primary_key=True)
    scraper = Column(Text, primary_key=True)

    paper = relationship("Paper", back_populates="paper_scraper")


t_paper_topic = Table(
    "paper_topic",
    metadata,
    Column("paper_id", ForeignKey("paper.paper_id"), primary_key=True),
    Column("topic_id", ForeignKey("topic.topic_id"), primary_key=True),
)


class Release(Base):
    __tablename__ = "release"
    __table_args__ = (UniqueConstraint("venue_id", "volume"),)

    date = Column(Integer, nullable=False)
    date_precision = Column(Integer, nullable=False)
    volume = Column(Text, nullable=False)
    release_id = Column(Integer, primary_key=True)
    venue_id = Column(ForeignKey("venue.venue_id"))
    publisher = Column(Text)

    paper = relationship(
        "Paper", secondary="paper_release", back_populates="release"
    )
    venue = relationship("Venue", back_populates="release")


class VenueAlias(Base):
    __tablename__ = "venue_alias"

    alias = Column(Text, primary_key=True, nullable=False)
    venue_id = Column(ForeignKey("venue.venue_id"), primary_key=True)

    venue = relationship("Venue", back_populates="venue_alias")


class VenueLink(Base):
    __tablename__ = "venue_link"

    type = Column(Text, primary_key=True, nullable=False)
    link = Column(Text, primary_key=True, nullable=False)
    venue_id = Column(ForeignKey("venue.venue_id"), primary_key=True)

    venue = relationship("Venue", back_populates="venue_link")


t_paper_author_institution = Table(
    "paper_author_institution",
    metadata,
    Column("paper_id", Integer, primary_key=True),
    Column("author_id", Integer, primary_key=True),
    Column(
        "institution_id",
        ForeignKey("institution.institution_id"),
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
