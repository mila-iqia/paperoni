PRAGMA foreign_keys=ON;

-- Updated schema using INTEGER PRIMARY KEY AUTOINCREMENT for better usability

-- A topic or keyword, like Computer Science, Theory, Large Language Model, etc.
CREATE TABLE IF NOT EXISTS topic (
	topic_id INTEGER PRIMARY KEY AUTOINCREMENT,
	-- The name of the topic
	name TEXT NOT NULL
);

-- An author
CREATE TABLE IF NOT EXISTS author (
	author_id INTEGER PRIMARY KEY AUTOINCREMENT,
	-- Name of the author
	name TEXT NOT NULL
);

-- An institution
CREATE TABLE IF NOT EXISTS institution (
	institution_id INTEGER PRIMARY KEY AUTOINCREMENT,
	-- Name of the institution
	name TEXT NOT NULL,
	-- Institution category, namely whether it is academia or industry
	category TEXT NOT NULL DEFAULT 'unknown',
	CHECK (category in ('unknown', 'academia', 'industry'))
);

-- A venue (conference, journal, workshop, etc.)
CREATE TABLE IF NOT EXISTS venue (
	venue_id INTEGER PRIMARY KEY AUTOINCREMENT,
	-- Type of venue: "conference", "journal", "workshop", etc.
	type TEXT,
	-- Name of the venue
	name TEXT NOT NULL,
	-- Series name (e.g. "Advances in Neural Information Processing Systems")
	series TEXT,
	-- Date of the venue (Unix timestamp)
	date INTEGER NOT NULL,
	-- Precision of the date: 0=unknown, 1=year, 2=month, 3=day
	date_precision INTEGER NOT NULL,
	-- Volume number
	volume TEXT,
	-- Publisher name
	publisher TEXT,
	-- Whether the venue is open access
	open INTEGER NOT NULL DEFAULT 0,
	-- Whether the venue is peer-reviewed
	peer_reviewed INTEGER NOT NULL DEFAULT 0,
	CHECK (open in (0, 1)),
	CHECK (peer_reviewed in (0, 1))
);

-- A release of a paper at a venue. A paper can have multiple releases
-- (e.g. preprint on ArXiv, then published at a conference, then published
-- in a journal). Each release is separate.
CREATE TABLE IF NOT EXISTS release (
	release_id INTEGER PRIMARY KEY AUTOINCREMENT,
	-- The venue that the paper was published at
	venue_id INTEGER REFERENCES venue(venue_id) ON DELETE CASCADE,
	-- Status at the venue: "published", "submitted", "rejected", "poster",
	-- "spotlight", etc. Mainly for OpenReview scraping.
	status TEXT,
	-- Page range in the proceedings, e.g. 344-347
	pages TEXT
);

-- Maps papers to their authors
CREATE TABLE IF NOT EXISTS paper_author (
	paper_id INTEGER NOT NULL REFERENCES paper(paper_id) ON DELETE CASCADE,
	author_id INTEGER NOT NULL REFERENCES author(author_id) ON DELETE CASCADE,
	-- The author's position in the authors list (0 = first author, then 1, 2, ...)
	author_position INTEGER NOT NULL,
	-- The author name as it appears in this specific paper
	display_name TEXT NOT NULL,
	PRIMARY KEY (paper_id, author_id)
);

-- Paper
CREATE TABLE IF NOT EXISTS paper (
	paper_id INTEGER PRIMARY KEY AUTOINCREMENT,
	-- Title of the paper
	title TEXT,
	-- Abstract of the paper
	abstract TEXT
);

-- Paper Info
CREATE TABLE IF NOT EXISTS paper_info (
	paper_id INTEGER NOT NULL REFERENCES paper(paper_id) ON DELETE CASCADE,
	key TEXT NOT NULL,
	update_key TEXT,
	info JSON NOT NULL,
	acquired INTEGER NOT NULL,
	score REAL NOT NULL,
	PRIMARY KEY (paper_id, key)
);

-- Aliases the author is known by ("John Smith", "J. Smith", "John Z. Smith", etc.)
CREATE TABLE IF NOT EXISTS author_alias (
	author_id INTEGER REFERENCES author(author_id) ON DELETE CASCADE,
	-- The alias
	alias TEXT NOT NULL,
	PRIMARY KEY (author_id, alias)
);

-- Links and identifiers corresponding to an author, for example their ID
-- on Semantic Scholar, OpenReview, their personal website, etc.
CREATE TABLE IF NOT EXISTS author_link (
	author_id INTEGER REFERENCES author(author_id) ON DELETE CASCADE,
	-- Link/ID type: "url", external ID source, etc.
	type TEXT NOT NULL,
	-- A url, external ID, etc.
	link TEXT NOT NULL,
	PRIMARY KEY (author_id, type, link)
);

-- Aliases the institution is known by, e.g. "Montreal Institute for Learning Algorithms",
-- "Mila", "Mila - IQIA", etc. The canonical name is in the institution table.
CREATE TABLE IF NOT EXISTS institution_alias (
	-- The institution
	institution_id INTEGER REFERENCES institution(institution_id) ON DELETE CASCADE,
	-- The alias
	alias TEXT NOT NULL,
	PRIMARY KEY (institution_id, alias)
);

-- Aliases the venue is known by, e.g. "NeurIPS", "NIPS", "Neural Information Processing Systems"
CREATE TABLE IF NOT EXISTS venue_alias (
	venue_id INTEGER REFERENCES venue(venue_id) ON DELETE CASCADE,
	-- The alias
	alias TEXT NOT NULL,
	PRIMARY KEY (venue_id, alias)
);

-- Links and identifiers corresponding to a venue, for example its website,
-- ISSN, etc.
CREATE TABLE IF NOT EXISTS venue_link (
	venue_id INTEGER REFERENCES venue(venue_id) ON DELETE CASCADE,
	-- Link/ID type: "url", "issn", etc.
	type TEXT NOT NULL,
	-- A url, ISSN, etc.
	link TEXT NOT NULL,
	PRIMARY KEY (venue_id, type, link)
);

-- Maps paper authors to their affiliations. This represents the affiliations that are
-- written under the authors in the paper, which is typically the institution they were
-- affiliated to at the time of doing the research, but may differ from their affiliation
-- at the time of publication (which is in the author_institution table for some authors).
CREATE TABLE IF NOT EXISTS paper_author_institution (
	paper_id INTEGER NOT NULL REFERENCES paper(paper_id) ON DELETE CASCADE,
	author_id INTEGER NOT NULL REFERENCES author(author_id) ON DELETE CASCADE,
	institution_id INTEGER NOT NULL REFERENCES institution(institution_id) ON DELETE CASCADE,
	PRIMARY KEY (paper_id, author_id, institution_id)
);

-- Maps a paper to its releases. For example, a paper may have a preprint on ArXiv,
-- have been submitted but not published to ICML, and then published at ICLR, which
-- corresponds to three different releases, pointing to three different venues.
CREATE TABLE IF NOT EXISTS paper_release (
	paper_id INTEGER REFERENCES paper(paper_id) ON DELETE CASCADE,
	release_id INTEGER REFERENCES release(release_id) ON DELETE CASCADE,
	PRIMARY KEY (paper_id, release_id)
);

-- Maps a paper to its topics/keywords
CREATE TABLE IF NOT EXISTS paper_topic (
	paper_id INTEGER REFERENCES paper(paper_id) ON DELETE CASCADE,
	topic_id INTEGER REFERENCES topic(topic_id) ON DELETE CASCADE,
	PRIMARY KEY (paper_id, topic_id)
);

-- Links and identifiers corresponding to a paper, for example its DOI,
-- arXiv ID, or a link to the PDF.
CREATE TABLE IF NOT EXISTS paper_link (
	paper_id INTEGER REFERENCES paper(paper_id) ON DELETE CASCADE,
	-- Link/ID type: "url", "arxiv", "doi", etc.
	type TEXT NOT NULL,
	-- Link data: a url, arxiv ID, DOI, etc.
	link TEXT NOT NULL,
	PRIMARY KEY (paper_id, type, link)
);

-- Flags associated to papers (set by Paperoni users)
CREATE TABLE IF NOT EXISTS paper_flag (
	paper_id INTEGER REFERENCES paper(paper_id) ON DELETE CASCADE,
	-- Name of the flag (e.g. "validated")
	flag_name TEXT NOT NULL,
	-- Boolean value of the flag
	flag INTEGER NOT NULL DEFAULT 0,
	CHECK (flag in (0, 1)),
	PRIMARY KEY (paper_id, flag_name)
);
