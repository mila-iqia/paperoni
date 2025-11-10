from .classes import Paper


def paper_has_updated(paper: Paper, new_paper: Paper) -> bool:
    # We only check the links list because it is purely incremental; checking the
    # title or the authors will cause the paper to be updated every time if several
    # sources have slight disagreements
    return bool({link for link in new_paper.links} - {link for link in paper.links})

    # return (
    #     normalize_title(paper.title) != normalize_title(new_paper.title)
    #     # We do not check the authors name as a minor name change would flag the
    #     # paper as updated
    #     or len({author.display_name for author in paper.authors})
    #     != len({author.display_name for author in new_paper.authors})
    #     # There are new links in the new paper
    #     or bool({link for link in new_paper.links} - {link for link in paper.links})
    # )
