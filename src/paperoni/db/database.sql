PRAGMA foreign_keys=ON;

-- Note about the BLOB PRIMARY KEYs: they should all be 128 bits, which does not
-- fit in any of SQLite's integer types. In a DB that has a UUID type, that would
-- be the proper datatype to use instead.

-- Paper
CREATE TABLE IF NOT EXISTS paper (
	paper_id BLOB PRIMARY KEY,
	-- Title of the paper
	title TEXT,
	-- Squashed title for easier merge, e.g. thefundamentalsofdeeplearning
	squashed TEXT,
	-- Abstract of the paper
	abstract TEXT,
	-- Current number of citations
	citation_count INTEGER,
	-- Quality of the information (used when merging entries)
	quality INTEGER NOT NULL DEFAULT 0
);

-- Links and identifiers corresponding to a paper, for example its DOI,
-- arXiv ID, or a link to the PDF.
CREATE TABLE IF NOT EXISTS paper_link (
	paper_id BLOB REFERENCES paper(paper_id) ON DELETE CASCADE,
	-- Link/ID type: "url", "arxiv", "doi", etc.
	type TEXT NOT NULL,
	-- Link data: a url, arxiv ID, DOI, etc.
	link TEXT NOT NULL,
	PRIMARY KEY (paper_id, type, link)
);

-- Flags associated to papers (set by Paperoni users)
CREATE TABLE IF NOT EXISTS paper_flag (
	paper_id BLOB REFERENCES paper(paper_id) ON DELETE CASCADE,
	-- Name of the flag (e.g. "validated")
	flag_name TEXT NOT NULL,
	-- Boolean value of the flag
	flag INTEGER NOT NULL DEFAULT 0,
	CHECK (flag in (0, 1)),
	PRIMARY KEY (paper_id, flag_name)
);

-- An author
CREATE TABLE IF NOT EXISTS author (
	author_id BLOB PRIMARY KEY,
	-- Name of the author
	name TEXT NOT NULL,
	-- Quality of the information (used when merging entries)
	quality INTEGER NOT NULL DEFAULT 0
);

-- Links and identifiers corresponding to an author, for example their ID
-- on Semantic Scholar, OpenReview, their personal website, etc.
CREATE TABLE IF NOT EXISTS author_link (
	author_id BLOB REFERENCES author(author_id) ON DELETE CASCADE,
	-- Link/ID type: "url", external ID source, etc.
	type TEXT NOT NULL,
	-- A url, external ID, etc.
	link TEXT NOT NULL,
	PRIMARY KEY (author_id, type, link)
);

-- Aliases the author is known by ("John Smith", "J. Smith", "John Z. Smith", etc.)
-- The canonical name for the author is in the author table. Aliases are used during
-- data acquisition to link papers to the right authors.
CREATE TABLE IF NOT EXISTS author_alias (
	author_id BLOB REFERENCES author(author_id) ON DELETE CASCADE,
	-- The alias
	alias TEXT NOT NULL,
	PRIMARY KEY (author_id, alias)
);

-- Describes an author's *temporal* affiliation to an institution. This is distinct
-- from the paper_author_institution table which documents the institution(s) that
-- an author lists on a specific paper (which may not be the same).
CREATE TABLE IF NOT EXISTS author_institution (
	author_id BLOB REFERENCES author(author_id) ON DELETE CASCADE,
	-- The institution the author works/worked at
	institution_id BLOB REFERENCES institution(institution_id) ON DELETE CASCADE,
	-- Their role at that institution: "professor", "PhD student" ...
	-- If an author has had multiple roles, they will have multiple entries in this table
	role TEXT NOT NULL,
	-- UNIX timestamp representing the time they started at the institution
	start_date UNSIGNED BIG INT NOT NULL,
	-- UNIX timestamp representing the time they left, or NULL if they are still there
	end_date UNSIGNED BIG INT,
	PRIMARY KEY (author_id, institution_id, role, start_date)
);

-- Publication venue: a journal, a conference, a book -- anything one or more papers
-- may be published in.
CREATE TABLE IF NOT EXISTS venue (
	venue_id BLOB PRIMARY KEY,
	-- Name of the venue
	name TEXT NOT NULL,
	-- Venue type: one of "journal", "conference", "book" ...
	type TEXT,
	-- Conference/journal series
	series TEXT,
	-- Date of publication as a UNIX timestamp
	date UNSIGNED BIG INT NOT NULL,
	-- 0, 1, 2 or 3
	-- 0: We don't actually know when this was published: disregard the date
	-- 1: The date represents a year (anytime during that year)
	-- 2: Month
	-- 3: Day
	date_precision UNSIGNED INT NOT NULL,
	-- Volume number of the journal or conference
	volume TEXT,
	-- Name of the publisher
	publisher TEXT,
	-- Whether this is an open access venue (might not be in use right now)
	open INTEGER NOT NULL DEFAULT 0,
	-- Whether papers at this venue undergo peer review (might not be in use right now)
	peer_reviewed INTEGER NOT NULL DEFAULT 0,
	-- Quality of the information (used when merging entries)
	quality INTEGER NOT NULL DEFAULT 0,
	CHECK (open in (0, 1)),
	CHECK (peer_reviewed in (0, 1))
);

-- Links and identifiers corresponding to a venue, for example their URL,
-- their ID on OpenReview, etc.
CREATE TABLE IF NOT EXISTS venue_link (
	-- The venue
	venue_id BLOB REFERENCES venue(venue_id) ON DELETE CASCADE,
	-- The link type: "url", external ID source, etc.
	type TEXT NOT NULL,
	-- A url, external ID, etc.
	link TEXT NOT NULL,
	PRIMARY KEY (venue_id, type, link)
);

-- Aliases the venue is known by ("Neural Information Processing Systems",
-- "NeurIPS", etc.)
CREATE TABLE IF NOT EXISTS venue_alias (
	-- The venue
	venue_id BLOB REFERENCES venue(venue_id) ON DELETE CASCADE,
	-- The alias for that venue
	alias TEXT NOT NULL,
	PRIMARY KEY (venue_id, alias)
);

-- Concrete data regarding a publication: where at, its status, page range
-- It should probably be merged with paper_release, I'm not sure why it's
-- separate.
CREATE TABLE IF NOT EXISTS release (
	release_id BLOB PRIMARY KEY,
	-- The venue that the paper was published at
	venue_id BLOB REFERENCES venue(venue_id) ON DELETE CASCADE,
	-- Status at the venue: "published", "submitted", "rejected", "poster",
	-- "spotlight", etc. Mainly for OpenReview scraping.
	status TEXT,
	-- Page range in the proceedings, e.g. 344-347
	pages TEXT
);

-- A topic or keyword, like Computer Science, Theory, Large Language Model, etc.
CREATE TABLE IF NOT EXISTS topic (
	topic_id BLOB PRIMARY KEY,
	-- The name of the topic
	topic TEXT NOT NULL,
	-- Optionally, a parent topic that encompasses this topic, for example the
	-- parent of Artificial Intelligence might be Computer Science
	parent BLOB REFERENCES topic(topic_id) ON DELETE CASCADE
);

-- An institution
CREATE TABLE IF NOT EXISTS institution (
	institution_id BLOB PRIMARY KEY,
	-- Name of the institution
	name TEXT NOT NULL,
	-- Institution category, namely whether it is academia or industry
	category TEXT NOT NULL DEFAULT 'unknown',
	CHECK (category in ('unknown', 'academia', 'industry'))
);

-- Aliases the institution is known by, e.g. "Montreal Institute for Learning Algorithms",
-- "Mila", "Mila - IQIA", etc. The canonical name is in the institution table.
CREATE TABLE IF NOT EXISTS institution_alias (
	-- The institution
	institution_id BLOB REFERENCES institution(institution_id) ON DELETE CASCADE,
	-- The alias
	alias TEXT NOT NULL,
	PRIMARY KEY (institution_id, alias)
);

-- Maps papers to their authors
CREATE TABLE IF NOT EXISTS paper_author (
	paper_id BLOB NOT NULL REFERENCES paper(paper_id) ON DELETE CASCADE,
	author_id BLOB NOT NULL REFERENCES author(author_id) ON DELETE CASCADE,
	-- The author's position in the authors list (0 = first author, then 1, 2, ...)
	author_position UNSIGNED INT NOT NULL,
	PRIMARY KEY (paper_id, author_id)
);

-- Maps paper authors to their affiliations. This represents the affiliations that are
-- written under the authors in the paper, which is typically the institution they were
-- affiliated to at the time of doing the research, but may differ from their affiliation
-- at the time of publication (which is in the author_institution table for some authors).
CREATE TABLE IF NOT EXISTS paper_author_institution (
	paper_id BLOB NOT NULL REFERENCES paper(paper_id) ON DELETE CASCADE,
	author_id BLOB NOT NULL REFERENCES author(author_id) ON DELETE CASCADE,
	institution_id BLOB NOT NULL REFERENCES institution(institution_id) ON DELETE CASCADE,
	PRIMARY KEY (paper_id, author_id, institution_id)
);

-- Maps a paper to its releases. For example, a paper may have a preprint on ArXiv,
-- have been submitted but not published to ICML, and then published at ICLR, which
-- corresponds to three different releases, pointing to three different venues.
CREATE TABLE IF NOT EXISTS paper_release (
	paper_id BLOB REFERENCES paper(paper_id) ON DELETE CASCADE,
	release_id BLOB REFERENCES release(release_id) ON DELETE CASCADE,
	PRIMARY KEY (paper_id, release_id)
);

-- Maps a paper to its topics/keywords
CREATE TABLE IF NOT EXISTS paper_topic (
	paper_id BLOB REFERENCES paper(paper_id) ON DELETE CASCADE,
	topic_id BLOB REFERENCES topic(topic_id) ON DELETE CASCADE,
	PRIMARY KEY (paper_id, topic_id)
);

-- Accounting table to keep track of which scraper contributed which rows
CREATE TABLE IF NOT EXISTS scraper (
	-- Represents an ID in one of the other tables
	hashid BLOB NOT NULL,
	-- Name of the scraper
	scraper TEXT NOT NULL,
	-- Note: latest date should take precedence
	date TEXT NOT NULL,
	PRIMARY KEY (hashid, scraper)
);

-- Accounting table to map certain IDs to canonical IDs. For example, if we merge
-- papers #14 and #37 into row #171, we will get two entries with #14 and #37 in
-- hashid and #171 in canonical.
CREATE TABLE IF NOT EXISTS canonical_id (
	hashid BLOB NOT NULL PRIMARY KEY,
	canonical BLOB
);


-- IDs scraped by semantic scholar, openreview, etc.
CREATE TABLE IF NOT EXISTS author_scrape_ids (
	scraper TEXT NOT NULL,
	author_id BLOB REFERENCES author(author_id),
	scrape_id TEXT NOT NULL,
	active INTEGER NOT NULL DEFAULT 0,
	CHECK (active in (-1, 0, 1)),
	PRIMARY KEY (scraper, scrape_id)
);


-- Scrapers can store arbitrary data here
CREATE TABLE IF NOT EXISTS scraper_data (
	scraper TEXT NOT NULL,
	tag TEXT NOT NULL,
	data TEXT,
	date UNSIGNED BIG INT NOT NULL,
	PRIMARY KEY (scraper, tag)
);
