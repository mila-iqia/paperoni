import http.client
import json
import re
import urllib.parse

from .utils import PaperoniError


class QueryError(PaperoniError):
    pass


def reconstruct_abstract(inverted):
    """Reconstruct a string from a {word: idx} dict."""
    idx = {}
    for word, ii in inverted.items():
        for i in ii:
            idx[i] = word
    words = [word for i, word in sorted(idx.items())]
    return " ".join(words)


class QueryManager:
    """Class to query the Microsoft Academic database.

    An API key is needed to query the API.
    """

    def __init__(self, key):
        self.key = key
        self.headers = {
            # Request headers
            "Ocp-Apim-Subscription-Key": f"{key}",
        }
        self.conn = http.client.HTTPSConnection(
            "api.labs.cognitive.microsoft.com"
        )

    def interpret(self, query, offset=0, count=10, **params):
        params = urllib.parse.urlencode(
            {
                # Request parameters
                "query": f"{query}",
                "model": "latest",
                "complete": 1,
                "count": str(count),
                "offset": str(offset),
                **params,
            }
        )

        self.conn.request(
            "GET", f"/academic/v1.0/interpret?{params}", "{body}", self.headers
        )
        response = self.conn.getresponse()
        data = response.read()
        jdata = json.loads(data)
        if "interpretations" not in jdata:
            print(jdata)
        interpretations = jdata["interpretations"]
        results = []
        for interp in interpretations:
            for rule in interp["rules"]:
                assert rule["name"] == "#GetPapers"
                assert rule["output"]["type"] == "query"
                results.append(rule["output"]["value"])
        return results

    def evaluate(self, expr, attrs, offset=0, count=10, **params):
        params = {k: v for k, v in params.items() if v is not None}
        params = urllib.parse.urlencode(
            {
                # Request parameters
                "expr": f"{expr}",
                "model": "latest",
                "count": str(count),
                "offset": str(offset),
                "attributes": f"{attrs}",
                **params,
            }
        )

        self.conn.request(
            "GET", f"/academic/v1.0/evaluate?{params}", "{body}", self.headers
        )
        response = self.conn.getresponse()
        data = response.read()
        jdata = json.loads(data)
        if "error" in jdata:
            raise QueryError(jdata["error"]["message"])
        if "InnerException" in jdata:
            raise QueryError(jdata["Message"])
        entities = jdata["entities"]
        return [self.clean(x) for x in entities]

    def clean(self, entity):
        """Clean up a result.

        The inverted abstract is replaced by the actual abstract and the author
        list is sorted.
        """
        iabstract = entity.get("IA", {}).get("InvertedIndex", {})
        entity["abstract"] = reconstruct_abstract(iabstract)
        entity["AA"] = list(sorted(entity["AA"], key=lambda auth: auth["S"]))
        for auth in entity["AA"]:
            del auth["S"]
        if "IA" in entity:
            del entity["IA"]
        return entity

    def _q_author(self, author):
        if isinstance(author, list):
            if len(author) == 1:
                return self._q_author(author[0])
            else:
                results = ",".join(self._q_author(a) for a in author)
                return f"Or({results})"
        elif isinstance(author, int):
            return f"Composite(AA.AuId={author})"
        else:
            author = author.lower()
            return f"Composite(AA.AuN='{author}')"

    def _q_paper_id(self, paper_id):
        return f"Id={paper_id}"

    def _q_title(self, title):
        title = title.lower()
        title = re.split(r"\W+", title)
        words = ",".join(f"W='{w}'" for w in title)
        return words

    def _q_words(self, query):
        query = query.lower()
        query = re.split(r"\W+", query)
        words = ",".join(f"OR(W='{w}',AW='{w}')" for w in query)
        return words

    def _q_interpret(self, query):
        queries = self.interpret(query=f"{query}", count=1)
        return queries[0]

    def _q_institution(self, inst):
        return f"Composite(AA.AfN='{inst}')"

    def _q_venue(self, venue):
        parts = [
            f"Composite(C.CN='{venue}')",
            f"Composite(J.JN='{venue}')",
        ]
        parts = ",".join(parts)
        return f"OR({parts})"

    def _q_keywords(self, query):
        qs = [f"Composite(F.FN='{kw}')" for kw in query]
        return ",".join(qs)

    def _q_daterange(self, r):
        start, end = r
        parts = []
        if start:
            parts.append(f"D>='{start}'")
        if end:
            parts.append(f"D<='{end}'")
        return ",".join(parts)

    def query(self, q, verbose=False, **params):
        """Run a query with the given parameters.

        Arguments:
            q: A query dictionary with any or all of these keys, which
               are combined using the AND operator.
                * author: Search for an author.
                * title: Words in the title.
                * words: Words in the title or abstract.
                * institution: Search papers from an institution.
                * keywords: List of paper keywords.
                * daterange: A tuple of (startdate, enddate), either of
                  which can be None.
            params: Parameters for the query such as limit and offset.
        """
        parts = []
        for k, v in q.items():
            if v is None:
                continue
            method_name = f"_q_{k}"
            part = getattr(self, method_name)(v)
            parts.append(part)

        expr = ",".join(p for p in parts if p)
        expr = f"And({expr})"
        if verbose:
            print(expr)
        return self.evaluate(expr, **params)
