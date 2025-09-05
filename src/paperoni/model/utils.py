from paperoni.model.classes import Paper


def paper_has_updated(paper: Paper, new_paper: Paper) -> bool:
    return (
        paper.title != new_paper.title
        or {author.display_name for author in paper.authors}
        != {author.display_name for author in new_paper.authors}
        or {link for link in paper.links} != {link for link in new_paper.links}
    )
