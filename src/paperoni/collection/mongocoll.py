from dataclasses import field
from datetime import date, datetime
from typing import AsyncGenerator, Iterable, Union

from bson import ObjectId
from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorCollection,
    AsyncIOMotorDatabase,
)
from pymongo.errors import DuplicateKeyError
from serieux import AllowExtras, deserialize, serialize
from serieux.features.encrypt import Secret

from ..model.classes import (
    CollectionMixin,
    CollectionPaper as CollectionPaper,
    Institution,
    Link,
    Paper,
    PaperAuthor,
    dataclass,
)
from ..utils import (
    normalize_institution,
    normalize_name,
    normalize_title,
    normalize_venue,
)
from .abc import PaperCollection, _id_types


@dataclass
class MongoMixin(CollectionMixin):
    id: str = None
    # Need to use str for _id because ObjectId throws an error:
    # serieux.exc.SchemaError: At path (at root): Cannot deserialize union type
    # `typing.Union[str, bson.objectid.ObjectId, NoneType]`, because no rule is
    # defined to discriminate `<class 'bson.objectid.ObjectId'>` from other
    # types.
    _id: str = None

    def __post_init__(self):
        _id = self._id or self.id
        self._id: ObjectId = ObjectId(_id) if _id else None
        self.id = self._id

    @classmethod
    def _filter_fields(cls, obj: dict) -> dict:
        return {k: v for k, v in obj.items() if k in cls.__dataclass_fields__}

    @classmethod
    def serieux_deserialize(cls, obj: dict, ctx, call_next):
        obj = obj.copy()
        obj["_id"] = str(obj["_id"]) if obj.get("_id", None) else None
        return call_next(AllowExtras[cls], obj, ctx)

    @classmethod
    def serieux_serialize(cls, obj, ctx, call_next):
        serialized = call_next(cls, obj, ctx)

        if serialized["_id"] is None:
            del serialized["_id"]
        else:
            serialized["id"] = serialized["_id"]

        return serialized


@dataclass
class NormalizedMixin:
    @classmethod
    def cast(cls, obj: Union["NormalizedMixin", dict]) -> "NormalizedMixin":
        if isinstance(obj, cls):
            return obj

        try:
            fields = vars(obj)
        except TypeError:
            fields = obj

        return cls(**cls._filter_fields(fields))

    @classmethod
    def _filter_fields(cls, obj: dict) -> dict:
        return {k: v for k, v in obj.items() if k in cls.__dataclass_fields__}


@dataclass
class NormalizedInstitution(Institution, NormalizedMixin):
    _norm_name: str = field(repr=False, compare=False, default=None)

    def __post_init__(self):
        self._norm_name = normalize_institution(self.name)


@dataclass
class NormalizedPaperAuthor(PaperAuthor, NormalizedMixin):
    affiliations: list[NormalizedInstitution] = field(default_factory=list)
    _norm_display_name: str = field(repr=False, compare=False, default=None)

    def __post_init__(self):
        self.affiliations: list[NormalizedInstitution] = [
            NormalizedInstitution.cast(a) for a in self.affiliations
        ]
        self._norm_display_name = normalize_name(self.display_name)


@dataclass
class NormalizedPaper(Paper, NormalizedMixin):
    authors: list[NormalizedPaperAuthor] = field(default_factory=list)
    _norm_title: str = field(repr=False, compare=False, default=None)

    def __post_init__(self):
        self.authors: list[NormalizedPaperAuthor] = [
            NormalizedPaperAuthor.cast(a) for a in self.authors
        ]
        self._norm_title = normalize_title(self.title)


@dataclass
class MongoPaper(CollectionPaper, NormalizedPaper, MongoMixin):
    # TODO: check if there is a way to use serieux_deserialize recursively
    # through all the parents
    @classmethod
    def serieux_deserialize(cls, obj, ctx, call_next):
        fields: dict = {}
        for parent in cls.__bases__:
            fields.update(vars(deserialize(AllowExtras[parent], obj, ctx)))
        return cls(**fields)

    @classmethod
    def serieux_serialize(cls, obj: "MongoPaper", ctx, call_next):
        serialized = {}
        for parent in cls.__bases__:
            serialized.update(serialize(parent, obj, ctx))
        return serialized


@dataclass
class MongoCollection(PaperCollection):
    """Async MongoDB implementation of PaperCollection using motor."""

    cluster_uri: str = "localhost:27017"
    user: Secret[str] = None
    password: Secret[str] = None
    connection_string: str = "mongodb://{cluster_uri}"
    database: str = "paperoni"
    collection: str = "collection"
    exclusions_collection: str = "exclusions"

    def __post_init__(self):
        self.connection_string = self.connection_string.format(
            user=self.user,
            password=self.password,
            cluster_uri=self.cluster_uri,
        )
        self._client: AsyncIOMotorClient = None
        self._database: AsyncIOMotorDatabase = None
        self._collection: AsyncIOMotorCollection = None
        self._exclusions: AsyncIOMotorCollection = None

    async def _ensure_connection(self):
        """Ensure MongoDB connection is established."""
        if self._client is None:
            self._client = AsyncIOMotorClient(self.connection_string)
            self._database = self._client[self.database]
            self._collection = self._database[self.collection]
            self._exclusions = self._database[self.exclusions_collection]

            # Create indexes for efficient searching
            await self._create_indexes()

    async def _create_indexes(self):
        """Create MongoDB indexes for efficient searching."""
        # Index on normalized title for fast title searches
        await self._collection.create_index("_norm_title")

        # Index on links for fast link-based lookups
        await self._collection.create_index("links.type")
        await self._collection.create_index("links.link")

        # Index on author names for fast author searches
        await self._collection.create_index("authors._norm_display_name")

        # Index on institution names for fast institution searches
        await self._collection.create_index("authors.affiliations._norm_name")

        # Index on venue names for fast venue searches
        await self._collection.create_index("releases.venue.name")
        await self._collection.create_index("releases.venue.short_name")
        await self._collection.create_index("releases.venue.aliases")

        # Index on release dates for fast date-based searches
        await self._collection.create_index("releases.venue.date")

        # Index on flags for fast flag-based searches
        await self._collection.create_index("flags")

        # Index on exclusions
        await self._exclusions.create_index("link", unique=True)

    async def exclusions(self) -> set[str]:
        """Get the set of excluded paper identifiers."""
        await self._ensure_connection()
        exclusions = {doc["link"] async for doc in self._exclusions.find({})}
        return exclusions

    async def add_papers(self, papers: Iterable[Paper | MongoPaper]) -> int:
        """Add papers to the collection."""
        await self._ensure_connection()
        added = 0

        for p in papers:
            for link in p.links:
                if await self._exclusions.find_one({"link": f"{link.type}:{link.link}"}):
                    break

            else:
                # Handle existing papers
                existing_paper: MongoPaper = None
                if isinstance(p, CollectionMixin) and (
                    existing_paper := await self._collection.find_one({"_id": p.id})
                ):
                    existing_paper = deserialize(MongoPaper, existing_paper)
                    if existing_paper.version >= p.version:
                        # Paper has been updated since last time it was fetched.
                        # Do not replace it.
                        continue
                    p.version = datetime.now()
                    await self._collection.replace_one(
                        {"_id": p.id}, serialize(MongoPaper, p)
                    )

                else:
                    p = MongoPaper.make_collection_item(p)
                    assert not await self._collection.find_one({"_id": p.id})
                    await self._collection.insert_one(serialize(MongoPaper, p))

                added += 1

        return added

    async def exclude_papers(self, papers: Iterable[Paper]) -> None:
        """Exclude papers from the collection."""
        await self._ensure_connection()

        papers_links = set()
        for paper in papers:
            for link in getattr(paper, "links", []):
                if link.type in _id_types:
                    papers_links.add(f"{link.type}:{link.link}")

        if papers_links:
            try:
                await self._exclusions.insert_many(
                    ({"link": x} for x in papers_links), ordered=False
                )
            except DuplicateKeyError:
                # Some exclusions already exist, that's fine
                pass

    async def find_paper(self, paper: Paper) -> MongoPaper | None:
        """Find a paper in the collection by links or title."""
        await self._ensure_connection()

        # First try to find by links
        for link in paper.links:
            if doc := await self._collection.find_one(
                {"links": {"$elemMatch": serialize(Link, link)}}
            ):
                break
        else:
            # Then try to find by normalized title
            doc = await self._collection.find_one(
                {
                    "_norm_title": {
                        "$regex": normalize_title(paper.title),
                        "$options": "i",
                    }
                }
            )

        return deserialize(MongoPaper, doc) if doc else None

    async def find_by_id(self, paper_id: int) -> MongoPaper | None:
        """Find a paper in the collection by id."""
        await self._ensure_connection()
        doc = await self._collection.find_one({"_id": ObjectId(paper_id)})
        return deserialize(MongoPaper, doc) if doc else None

    async def edit_paper(self, paper: MongoPaper) -> None:
        """Edit an existing paper in the collection."""
        await self._ensure_connection()

        existing_paper = await self._collection.find_one({"_id": paper.id})
        if not existing_paper:
            raise ValueError(f"Paper with ID {paper.id} not found in collection")

        paper.version = datetime.now()
        result = await self._collection.replace_one(
            {"_id": paper.id}, serialize(MongoPaper, paper)
        )

        if result.matched_count == 0:
            raise ValueError(f"Paper with ID {paper.id} not found in collection")

    async def drop(self) -> None:
        """Drop the collection."""
        await self._ensure_connection()
        await self._client.drop_database(self.database)
        self._client = None
        self._database = None
        self._collection = None
        self._exclusions = None

    async def search(
        self,
        paper_id: ObjectId = None,
        title: str = None,
        institution: str = None,
        author: str = None,
        venue: str = None,
        start_date: date = None,
        end_date: date = None,
        include_flags: list[str] = None,
        exclude_flags: list[str] = None,
    ) -> AsyncGenerator[MongoPaper, None]:
        """Search for papers in the collection."""
        await self._ensure_connection()

        query = {}
        title = title and normalize_title(title)
        author = author and normalize_name(author)
        institution = institution and normalize_institution(institution)
        venue = venue and normalize_venue(venue)

        if paper_id is not None:
            query["_id"] = ObjectId(paper_id)

        if title:
            query["_norm_title"] = {"$regex": f".*{title}.*", "$options": "i"}

        if author:
            query["authors._norm_display_name"] = {
                "$regex": f".*{author}.*",
                "$options": "i",
            }

        if venue:
            # Match papers where any release has a venue name, short_name, or alias matching the search
            query["$or"] = [
                {"releases.venue.name": {"$regex": f".*{venue}.*", "$options": "i"}},
                {
                    "releases.venue.short_name": {
                        "$regex": f".*{venue}.*",
                        "$options": "i",
                    }
                },
                {"releases.venue.aliases": {"$regex": f".*{venue}.*", "$options": "i"}},
            ]

        # Date filtering: papers match if at least one release falls within the date range
        if start_date or end_date:
            date_query = {}
            if start_date:
                date_query["$gte"] = start_date
            if end_date:
                date_query["$lte"] = end_date

            # Match papers where at least one release date is in the range
            query["releases.venue.date"] = date_query

        # Flag filtering
        if include_flags:
            # All flags in include_flags must be present
            query["flags"] = {"$all": list(include_flags)}

        if exclude_flags:
            # None of the flags in exclude_flags should be present
            if "flags" in query:
                # If we already have a flags query from include_flags, combine them
                query["$and"] = [
                    {"flags": query["flags"]},
                    {"flags": {"$nin": list(exclude_flags)}},
                ]
                del query["flags"]
            else:
                query["flags"] = {"$nin": list(exclude_flags)}

        if institution:
            query["authors.affiliations._norm_name"] = {
                "$regex": f".*{institution}.*",
                "$options": "i",
            }

        async for doc in self._collection.find(query):
            yield deserialize(MongoPaper, doc)

    async def _commit(self) -> None:
        # Commits are done synchronously to collections operations
        pass

    def __len__(self) -> int:
        """Get the number of papers in the collection."""
        raise NotImplementedError(
            "Use 'await collection.count()' instead of len() for async MongoDB collection"
        )

    async def count(self) -> int:
        """Get the number of papers in the collection."""
        await self._ensure_connection()
        return await self._collection.count_documents({})
