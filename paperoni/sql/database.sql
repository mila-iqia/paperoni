PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS paper (
	paper_id INTEGER PRIMARY KEY AUTOINCREMENT,
	title TEXT,
	abstract TEXT,
	is_open_access SMALLINT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS paper_external_id (
	paper_id INTEGER REFERENCES paper(paper_id) ON DELETE CASCADE,
	external_id TEXT NOT NULL,
	UNIQUE (paper_id, external_id)
);

CREATE TABLE IF NOT EXISTS paper_url (
	paper_id INTEGER REFERENCES paper(paper_id) ON DELETE CASCADE,
	-- One of "HTML", "PDF", "TEXT" ...
	url_type TEXT NOT NULL,
	url TEXT NOT NULL,
	UNIQUE (paper_id, url_type, url)
);

CREATE TABLE IF NOT EXISTS author (
	author_id INTEGER PRIMARY KEY AUTOINCREMENT,
	author_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS author_external_id (
	author_id INTEGER REFERENCES author(author_id) ON DELETE CASCADE,
	author_external_id TEXT NOT NULL,
	UNIQUE (author_id, author_external_id)
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

CREATE TABLE IF NOT EXISTS author_url (
	author_id INTEGER REFERENCES author(author_id) ON DELETE CASCADE,
	url TEXT NOT NULL,
	is_homepage SMALLINT NOT NULL DEFAULT 0,
	UNIQUE (author_id, url, is_homepage)
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
	release_year UNSIGNED INT,
	volume TEXT,
	UNIQUE (venue_id, release_date, release_year, volume),
	-- Either date or year is required.
	CHECK (release_date IS NOT NULL OR release_year IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS field_of_study (
	field_of_study_id INTEGER PRIMARY KEY AUTOINCREMENT,
	field_of_study_name TEXT NOT NULL
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

CREATE TABLE IF NOT EXISTS paper_to_field_of_study (
	paper_id INTEGER REFERENCES paper(paper_id) ON DELETE CASCADE,
	field_of_study_id INTEGER REFERENCES field_of_study(field_of_study_id) ON DELETE CASCADE,
	PRIMARY KEY (paper_id, field_of_study_id)
);
