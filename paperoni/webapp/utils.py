import re
from datetime import datetime


class Confidence:
    """Compute a confidence level for how relevant a paper is.

    The confidence is computed on the authors list: their names and the institution(s)
    declared in their affiliations.

    Attributes:
        low_confidence_names: A set of names that we have low confidence about,
            typically because they have multiple homonyms.
        institution_name: A regex to match the name of the institution(s) that
            are relevant.
        boost_link_type: If this type of author_link is found, boost the author.
            For example, this may be a link to the author's bio or page on the
            website (e.g. "wpid_en", the Wordpress ID in the English language for
            this author)
    """

    def __init__(self, low_confidence_names, institution_name, boost_link_type):
        self.low_confidence_names = set(low_confidence_names)
        self.institution_name = re.compile(
            institution_name, flags=re.IGNORECASE
        )
        self.boost_link_type = boost_link_type

    def author_name_score(self, aliases):
        """Score the name of an author."""
        if any(a in self.low_confidence_names for a in aliases):
            return 1
        else:
            return 2

    def institution_score(self, institution):
        """Score an institution."""
        if self.institution_name.fullmatch(institution.name):
            return 10
        else:
            return 0

    def known_author_score(self, author, mindate, maxdate):
        """Score an author between the given dates (no institution score)."""
        for role in author.roles:
            if (
                datetime.fromtimestamp(role.start_date) < maxdate
                and (
                    not role.end_date
                    or datetime.fromtimestamp(role.end_date) > mindate
                )
                and self.institution_name.fullmatch(role.institution.name)
            ):
                return self.author_name_score(author.aliases)
        for lnk in author.links:
            if lnk.type == self.boost_link_type:
                return 0.5 * self.author_name_score(author.aliases)
        return 0

    def author_score(self, paper, paper_author):
        """Score an author."""
        dates = [
            datetime.fromtimestamp(release.venue.date)
            for release in paper.releases
        ]
        mindate = min(dates, default=datetime(year=2000, month=1, day=1))
        maxdate = max(dates, default=datetime(year=2000, month=1, day=1))
        return max(
            [
                self.institution_score(inst)
                for inst in paper_author.affiliations
            ],
            default=0,
        ) + self.known_author_score(paper_author.author, mindate, maxdate)

    def paper_score(self, paper):
        """Score a paper.

        Returns:
            (total_score, author_scores) where the author_scores are (author, score)
            tuples.
        """
        author_scores = [
            (auth, self.author_score(paper, auth)) for auth in paper.authors
        ]
        total_score = sum(x for _, x in author_scores)
        return total_score, author_scores
