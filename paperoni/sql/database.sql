PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS paper (
	paper_id INTEGER PRIMARY KEY AUTOINCREMENT,
	title TEXT,
	abstract TEXT,
	is_open_access SMALLINT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS paper_link (
	paper_id INTEGER REFERENCES paper(paper_id) ON DELETE CASCADE,
	-- "url", "arxiv", "doi", etc.
	link_type TEXT NOT NULL,
	-- A url, arxiv ID, DOI, etc.
	link TEXT NOT NULL,
	UNIQUE (paper_id, link_type, link)
);

CREATE TABLE IF NOT EXISTS author (
	author_id INTEGER PRIMARY KEY AUTOINCREMENT,
	author_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS author_link (
	author_id INTEGER REFERENCES author(author_id) ON DELETE CASCADE,
	-- "url", external ID source, etc.
	link_type TEXT NOT NULL,
	-- A url, external ID, etc.
	link TEXT NOT NULL,
	UNIQUE (author_id, link_type, link)
);

CREATE TABLE IF NOT EXISTS author_alias (
	author_id INTEGER REFERENCES author(author_id) ON DELETE CASCADE,
	alias TEXT NOT NULL,
	UNIQUE (author_id, alias)
);

CREATE TABLE IF NOT EXISTS author_affiliation (
	author_id INTEGER REFERENCES author(author_id) ON DELETE CASCADE,
	-- E.g. "UdeM", "McGill", "Mila" ...
	affiliation TEXT NOT NULL,
	-- E.g. "professor", "PhD student" ...
	role TEXT,
	-- Timestamp in seconds.
	start_date UNSIGNED BIG INT,
	-- Timestamp in seconds.
	end_date UNSIGNED BIG INT,
	UNIQUE (author_id, affiliation, role, start_date, end_date)
);

CREATE TABLE IF NOT EXISTS venue (
	venue_id INTEGER PRIMARY KEY AUTOINCREMENT,
	-- One of "journal", "conference", "book" ...
	venue_type TEXT,
	venue_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS release (
	release_id INTEGER PRIMARY KEY AUTOINCREMENT,
	venue_id INTEGER REFERENCES venue(venue_id) ON DELETE CASCADE,
	-- Timestamp in seconds.
	release_date UNSIGNED BIG INT,
	release_year UNSIGNED INT NOT NULL,
	volume TEXT,
	UNIQUE (venue_id, volume)
);

CREATE TABLE IF NOT EXISTS keyword (
	keyword_id INTEGER PRIMARY KEY AUTOINCREMENT,
	keyword TEXT NOT NULL,
	parent INTEGER REFERENCES keyword(keyword_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS paper_to_author (
	paper_id INTEGER REFERENCES paper(paper_id) ON DELETE CASCADE,
	author_id INTEGER REFERENCES author(author_id) ON DELETE CASCADE,
	-- Author position in paper authors list.
	author_position UNSIGNED INT NOT NULL,
	PRIMARY KEY (paper_id, author_id)
);

CREATE TABLE IF NOT EXISTS paper_to_release (
	paper_id INTEGER REFERENCES paper(paper_id) ON DELETE CASCADE,
	release_id INTEGER REFERENCES release(release_id) ON DELETE CASCADE,
	PRIMARY KEY (paper_id, release_id)
);

CREATE TABLE IF NOT EXISTS paper_to_keyword (
	paper_id INTEGER REFERENCES paper(paper_id) ON DELETE CASCADE,
	keyword_id INTEGER REFERENCES keyword(keyword_id) ON DELETE CASCADE,
	PRIMARY KEY (paper_id, keyword_id)
);
