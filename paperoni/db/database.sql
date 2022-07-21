PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS paper (
	paper_id INTEGER PRIMARY KEY AUTOINCREMENT,
	title TEXT,
	abstract TEXT,
	citation_count INTEGER
);

CREATE TABLE IF NOT EXISTS paper_link (
	paper_id INTEGER REFERENCES paper(paper_id) ON DELETE CASCADE,
	-- "url", "arxiv", "doi", etc.
	type TEXT NOT NULL,
	-- A url, arxiv ID, DOI, etc.
	link TEXT NOT NULL,
	PRIMARY KEY (paper_id, type, link)
);

CREATE TABLE IF NOT EXISTS paper_flag (
	paper_id INTEGER REFERENCES paper(paper_id) ON DELETE CASCADE,
	flag_name TEXT NOT NULL,
	flag INTEGER NOT NULL DEFAULT 0,
	CHECK (flag in (0, 1)),
	PRIMARY KEY (paper_id, flag_name)
);

CREATE TABLE IF NOT EXISTS author (
	author_id INTEGER PRIMARY KEY AUTOINCREMENT,
	name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS author_link (
	author_id INTEGER REFERENCES author(author_id) ON DELETE CASCADE,
	-- "url", external ID source, etc.
	type TEXT NOT NULL,
	-- A url, external ID, etc.
	link TEXT NOT NULL,
	PRIMARY KEY (author_id, type, link)
);

CREATE TABLE IF NOT EXISTS author_alias (
	author_id INTEGER REFERENCES author(author_id) ON DELETE CASCADE,
	alias TEXT NOT NULL,
	PRIMARY KEY (author_id, alias)
);

CREATE TABLE IF NOT EXISTS author_institution (
	author_id INTEGER REFERENCES author(author_id) ON DELETE CASCADE,
	-- E.g. "UdeM", "McGill", "Mila" ...
	institution_id INTEGER REFERENCES institution(institution_id) ON DELETE CASCADE,
	-- E.g. "professor", "PhD student" ...
	role TEXT NOT NULL,
	-- Timestamp in seconds.
	start_date UNSIGNED BIG INT NOT NULL,
	-- Timestamp in seconds.
	end_date UNSIGNED BIG INT,
	PRIMARY KEY (author_id, institution_id, role, start_date)
);

CREATE TABLE IF NOT EXISTS venue (
	venue_id INTEGER PRIMARY KEY AUTOINCREMENT,
	-- One of "journal", "conference", "book" ...
	type TEXT,
	name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS venue_link (
	venue_id INTEGER REFERENCES venue(venue_id) ON DELETE CASCADE,
	-- "url", external ID source, etc.
	type TEXT NOT NULL,
	-- A url, external ID, etc.
	link TEXT NOT NULL,
	PRIMARY KEY (venue_id, type, link)
);

CREATE TABLE IF NOT EXISTS venue_alias (
	venue_id INTEGER REFERENCES venue(venue_id) ON DELETE CASCADE,
	alias TEXT NOT NULL,
	PRIMARY KEY (venue_id, alias)
);

CREATE TABLE IF NOT EXISTS release (
	release_id INTEGER PRIMARY KEY AUTOINCREMENT,
	venue_id INTEGER REFERENCES venue(venue_id) ON DELETE CASCADE,
	-- Timestamp in seconds.
	date UNSIGNED BIG INT NOT NULL,
	date_precision UNSIGNED INT NOT NULL,
	volume TEXT,
	publisher TEXT
	-- UNIQUE (venue_id, volume)
);

CREATE TABLE IF NOT EXISTS topic (
	topic_id INTEGER PRIMARY KEY AUTOINCREMENT,
	topic TEXT NOT NULL,
	parent INTEGER REFERENCES topic(topic_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS institution (
	institution_id INTEGER PRIMARY KEY AUTOINCREMENT,
	name TEXT NOT NULL,
	category TEXT NOT NULL DEFAULT 'unknown',
	CHECK (category in ('unknown', 'academia', 'industry'))
);

CREATE TABLE IF NOT EXISTS institution_alias (
	institution_id INTEGER REFERENCES institution(institution_id) ON DELETE CASCADE,
	alias TEXT NOT NULL,
	PRIMARY KEY (institution_id, alias)
);

CREATE TABLE IF NOT EXISTS paper_author (
	paper_id INTEGER REFERENCES paper(paper_id) ON DELETE CASCADE,
	author_id INTEGER REFERENCES author(author_id) ON DELETE CASCADE,
	-- Author position in paper authors list.
	author_position UNSIGNED INT NOT NULL,
	PRIMARY KEY (paper_id, author_id)
);

CREATE TABLE IF NOT EXISTS paper_author_institution (
	paper_id INTEGER,
	author_id INTEGER,
	institution_id INTEGER REFERENCES institution(institution_id) ON DELETE CASCADE,
	FOREIGN KEY (paper_id, author_id) REFERENCES paper_author(paper_id, author_id) ON DELETE CASCADE,
	PRIMARY KEY (paper_id, author_id, institution_id)
);

CREATE TABLE IF NOT EXISTS paper_release (
	paper_id INTEGER REFERENCES paper(paper_id) ON DELETE CASCADE,
	release_id INTEGER REFERENCES release(release_id) ON DELETE CASCADE,
	PRIMARY KEY (paper_id, release_id)
);

CREATE TABLE IF NOT EXISTS paper_topic (
	paper_id INTEGER REFERENCES paper(paper_id) ON DELETE CASCADE,
	topic_id INTEGER REFERENCES topic(topic_id) ON DELETE CASCADE,
	PRIMARY KEY (paper_id, topic_id)
);

CREATE TABLE IF NOT EXISTS paper_scraper (
	paper_id INTEGER REFERENCES paper(paper_id) ON DELETE CASCADE,
	scraper TEXT,
	PRIMARY KEY (paper_id, scraper)
);
