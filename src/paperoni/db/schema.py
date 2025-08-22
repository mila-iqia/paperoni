from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Column,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    Table,
    Text,
    and_,
    text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()
metadata = Base.metadata


# Base Tables


class Topic(Base):
    __tablename__ = "topic"

    # Use auto-incrementing integer as primary key
    topic_id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)

    paper = relationship("Paper", secondary="paper_topic", back_populates="topic")


class Author(Base):
    __tablename__ = "author"

    # Use auto-incrementing integer as primary key for better usability
    author_id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)

    author_alias = relationship("AuthorAlias", back_populates="author")
    author_link = relationship("AuthorLink", back_populates="author")

    paper_author = relationship("PaperAuthor", back_populates="author")
    paper_author_institution = relationship(
        "PaperAuthorInstitution", back_populates="author"
    )

    @property
    def aliases(self):
        return [alias.alias for alias in self.author_alias]

    @property
    def links(self):
        return self.author_link


class Institution(Base):
    __tablename__ = "institution"
    __table_args__ = (
        CheckConstraint("category in ('academia', 'industry', 'unknown')"),
    )

    # Use auto-incrementing integer as primary key
    institution_id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)
    category = Column(Text, nullable=False, server_default=text("'unknown'"))

    institution_alias = relationship("InstitutionAlias", back_populates="institution")

    paper_author_institution = relationship(
        "PaperAuthorInstitution", back_populates="institution"
    )

    @property
    def aliases(self):
        return [alias.alias for alias in self.institution_alias]


class Venue(Base):
    __tablename__ = "venue"
    __table_args__ = (
        CheckConstraint("open in (0, 1)"),
        CheckConstraint("peer_reviewed in (0, 1)"),
    )

    # Use auto-incrementing integer as primary key
    venue_id = Column(BigInteger, primary_key=True, autoincrement=True)
    type = Column(Text)
    name = Column(Text, nullable=False)
    series = Column(Text)
    date = Column(Integer, nullable=False)
    date_precision = Column(Integer, nullable=False)
    volume = Column(Text)
    publisher = Column(Text)
    open = Column(Integer, nullable=False, server_default=text("0"))
    peer_reviewed = Column(Integer, nullable=False, server_default=text("0"))

    venue_alias = relationship("VenueAlias", back_populates="venue")
    venue_link = relationship("VenueLink", back_populates="venue")

    release = relationship("Release", back_populates="venue")

    @property
    def aliases(self):
        return [alias.alias for alias in self.venue_alias]

    @property
    def links(self):
        return self.venue_link


class Release(Base):
    __tablename__ = "release"

    # Use auto-incrementing integer as primary key
    release_id = Column(BigInteger, primary_key=True, autoincrement=True)
    venue_id = Column(ForeignKey("venue.venue_id"))
    status = Column(Text)
    pages = Column(Text, nullable=True)

    venue = relationship("Venue", back_populates="release")

    paper = relationship("Paper", secondary="paper_release", back_populates="release")


class PaperAuthor(Base):
    __tablename__ = "paper_author"

    paper_id = Column(ForeignKey("paper.paper_id"), primary_key=True, nullable=False)
    author_id = Column(ForeignKey("author.author_id"), primary_key=True, nullable=False)
    author_position = Column(Integer, nullable=False)
    # Store the author name as it appears in this specific paper
    display_name = Column(Text, nullable=False)

    paper = relationship("Paper", back_populates="paper_author")
    author = relationship("Author", back_populates="paper_author")
    paper_author_institution = relationship(
        "PaperAuthorInstitution",
        primaryjoin=lambda: and_(
            PaperAuthor.paper_id == PaperAuthorInstitution.paper_id,
            PaperAuthor.author_id == PaperAuthorInstitution.author_id,
        ),
        back_populates="paper_author",
        foreign_keys=lambda: [
            PaperAuthorInstitution.paper_id,
            PaperAuthorInstitution.author_id,
        ],
    )

    @property
    def affiliations(self):
        return self.paper_author_institution


class Paper(Base):
    __tablename__ = "paper"

    # Use auto-incrementing integer as primary key
    paper_id = Column(BigInteger, primary_key=True, autoincrement=True)
    title = Column(Text)
    abstract = Column(Text)

    paper_author = relationship("PaperAuthor", back_populates="paper")
    release = relationship("Release", secondary="paper_release", back_populates="paper")
    topic = relationship("Topic", secondary="paper_topic", back_populates="paper")
    paper_link = relationship("PaperLink", back_populates="paper")
    paper_flag = relationship("PaperFlag", back_populates="paper")

    paper_author_institution = relationship(
        "PaperAuthorInstitution", back_populates="paper"
    )
    paper_info = relationship("PaperInfo", back_populates="paper")

    @property
    def authors(self):
        pas = [pa for pa in self.paper_author if pa.author]
        pas.sort(key=lambda pa: pa.author_position)
        return pas

    @property
    def releases(self):
        return self.release

    @property
    def topics(self):
        return self.topic

    @property
    def links(self):
        return self.paper_link

    @property
    def flags(self):
        return self.paper_flag


class PaperInfo(Base):
    __tablename__ = "paper_info"

    paper_id = Column(ForeignKey("paper.paper_id"), primary_key=True, nullable=False)
    key = Column(Text, primary_key=True, unique=True, nullable=False)
    update_key = Column(Text, unique=True, nullable=True)
    info = Column(JSON, nullable=False)
    acquired = Column(Integer, nullable=False)
    score = Column(Float, nullable=False)

    paper = relationship("Paper", back_populates="paper_info")


# Relationships


class AuthorAlias(Base):
    __tablename__ = "author_alias"

    alias = Column(Text, primary_key=True, nullable=False)
    author_id = Column(ForeignKey("author.author_id"), primary_key=True)

    author = relationship("Author", back_populates="author_alias")


class AuthorLink(Base):
    __tablename__ = "author_link"

    type = Column(Text, primary_key=True, nullable=False)
    link = Column(Text, primary_key=True, nullable=False)
    author_id = Column(ForeignKey("author.author_id"), primary_key=True)

    author = relationship("Author", back_populates="author_link")


class InstitutionAlias(Base):
    __tablename__ = "institution_alias"

    alias = Column(Text, primary_key=True, nullable=False)
    institution_id = Column(ForeignKey("institution.institution_id"), primary_key=True)

    institution = relationship("Institution", back_populates="institution_alias")


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


class PaperAuthorInstitution(Base):
    __tablename__ = "paper_author_institution"

    paper_id = Column(ForeignKey("paper.paper_id"), primary_key=True, nullable=False)
    author_id = Column(ForeignKey("author.author_id"), primary_key=True, nullable=False)
    institution_id = Column(
        ForeignKey("institution.institution_id"),
        primary_key=True,
        nullable=False,
    )

    paper = relationship("Paper", back_populates="paper_author_institution")
    author = relationship("Author", back_populates="paper_author_institution")
    institution = relationship("Institution", back_populates="paper_author_institution")

    paper_author = relationship(
        "PaperAuthor",
        primaryjoin=lambda: and_(
            PaperAuthor.paper_id == PaperAuthorInstitution.paper_id,
            PaperAuthor.author_id == PaperAuthorInstitution.author_id,
        ),
        back_populates="paper_author_institution",
        foreign_keys=lambda: [
            PaperAuthorInstitution.paper_id,
            PaperAuthorInstitution.author_id,
        ],
    )


t_paper_release = Table(
    "paper_release",
    metadata,
    Column("paper_id", ForeignKey("paper.paper_id"), primary_key=True),
    Column("release_id", ForeignKey("release.release_id"), primary_key=True),
)


t_paper_topic = Table(
    "paper_topic",
    metadata,
    Column("paper_id", ForeignKey("paper.paper_id"), primary_key=True),
    Column("topic_id", ForeignKey("topic.topic_id"), primary_key=True),
)


class PaperLink(Base):
    __tablename__ = "paper_link"

    type = Column(Text, primary_key=True, nullable=False)
    link = Column(Text, primary_key=True, nullable=False)
    paper_id = Column(ForeignKey("paper.paper_id"), primary_key=True)

    paper = relationship("Paper", back_populates="paper_link")


class PaperFlag(Base):
    __tablename__ = "paper_flag"
    __table_args__ = (CheckConstraint("flag in (0, 1)"),)

    flag_name = Column(Text, primary_key=True, nullable=False)
    flag = Column(Integer, nullable=False, server_default=text("0"))
    paper_id = Column(ForeignKey("paper.paper_id"), primary_key=True)

    paper = relationship("Paper", back_populates="paper_flag")
