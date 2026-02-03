from dataclasses import replace
from datetime import date, datetime
from typing import AsyncGenerator, Iterable

from bson import ObjectId
from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorCollection,
    AsyncIOMotorDatabase,
)
from ovld import Medley, call_next
from pymongo.errors import DuplicateKeyError
from serieux import Context, Serieux
from serieux.features.encrypt import Secret

from ..model.classes import (
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
    to_sync,
)
from .abc import PaperCollection
from .finder import extract_latest


class MongoSerieux(Medley):
    def serialize(self, t: type[Institution], obj: Institution, ctx: Context):
        rval = call_next(t, obj, ctx)
        rval["_norm_name"] = normalize_institution(obj.name)
        return rval

    def serialize(self, t: type[PaperAuthor], obj: PaperAuthor, ctx: Context):
        rval = call_next(t, obj, ctx)
        rval["_norm_display_name"] = normalize_name(obj.display_name)
        return rval

    def serialize(self, t: type[Paper], obj: Paper, ctx: Context):
        rval = call_next(t, obj, ctx)
        rval["_norm_title"] = normalize_title(obj.title)
        rval["_latest"] = list(extract_latest(obj))[0]
        if obj.id is not None:
            assert isinstance(obj.id, str)
            rval["_id"] = obj.id
            del rval["id"]
        return rval

    def deserialize(self, t: type[Paper], obj: dict, ctx: Context):
        obj = dict(obj)
        ident = obj.pop("_id", None)
        if ident is not None:
            obj["id"] = str(ident)
        return call_next(t, obj, ctx)


srx = (Serieux + MongoSerieux)()


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

        # Index on _latest for sorting by recency
        await self._collection.create_index([("_latest", -1)])

        # Index on exclusions
        await self._exclusions.create_index("link", unique=True)

    async def exclusions(self) -> set[str]:
        """Get the set of excluded paper identifiers."""
        await self._ensure_connection()
        exclusions = {doc["link"] async for doc in self._exclusions.find({})}
        return exclusions

    async def add_exclusions(self, exclusions: list[str]) -> None:
        """Add exclusion strings."""
        if not exclusions:
            return
        await self._ensure_connection()
        try:
            await self._exclusions.insert_many(
                ({"link": x} for x in exclusions), ordered=False
            )
        except DuplicateKeyError:
            # Some exclusions already exist, that's fine
            pass

    async def remove_exclusions(self, exclusions: list[str]) -> None:
        """Remove exclusion strings."""
        if not exclusions:
            return
        await self._ensure_connection()
        await self._exclusions.delete_many({"link": {"$in": exclusions}})

    async def is_excluded(self, s: str):
        """Return whether a link is excluded."""
        return await self._exclusions.find_one({"link": s})

    async def add_papers(
        self, papers: Iterable[Paper], force=False, ignore_exclusions=False
    ) -> list[int | str]:
        """Add papers to the collection."""
        await self._ensure_connection()
        added_ids = []

        if not ignore_exclusions:
            papers = await to_sync(self.filter_exclusions(papers))

        for p in papers:
            # Handle existing papers
            existing_paper: Paper = None
            if existing_paper := await self._collection.find_one({"_id": p.id}):
                existing_paper = srx.deserialize(Paper, existing_paper)
                if not force and existing_paper.version >= p.version:
                    # Paper has been updated since last time it was fetched.
                    # Do not replace it.
                    continue
                p.version = datetime.now()
                await self._collection.replace_one({"_id": p.id}, srx.serialize(Paper, p))

            elif p.id is not None:
                raise ValueError(f"Paper with ID {p.id} not found in collection")

            else:
                p.version = datetime.now()
                assert not await self._collection.find_one({"_id": p.id})
                result = await self._collection.insert_one(srx.serialize(Paper, p))
                p = replace(p, id=str(result.inserted_id))

            added_ids.append(p.id)

        return added_ids

    async def find_paper(self, paper: Paper) -> Paper | None:
        """Find a paper in the collection by links or title."""
        await self._ensure_connection()

        # First try to find by links
        for link in paper.links:
            if doc := await self._collection.find_one(
                {"links": {"$elemMatch": srx.serialize(Link, link)}}
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

        return srx.deserialize(Paper, doc) if doc else None

    async def find_by_id(self, paper_id: int) -> Paper | None:
        """Find a paper in the collection by id."""
        await self._ensure_connection()
        doc = await self._collection.find_one({"_id": ObjectId(paper_id)})
        return srx.deserialize(Paper, doc) if doc else None

    async def delete_ids(self, ids: list[int]) -> int:
        """Delete papers by ID."""
        await self._ensure_connection()
        result = await self._collection.delete_many(
            {"_id": {"$in": [ObjectId(i) for i in ids]}}
        )
        return result.deleted_count

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
    ) -> AsyncGenerator[Paper, None]:
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

        async for doc in self._collection.find(query).sort("_latest", -1):
            yield srx.deserialize(Paper, doc)

    def __len__(self) -> int:
        """Get the number of papers in the collection."""
        raise NotImplementedError(
            "Use 'await collection.count()' instead of len() for async MongoDB collection"
        )

    async def count(self) -> int:
        """Get the number of papers in the collection."""
        await self._ensure_connection()
        return await self._collection.count_documents({})
