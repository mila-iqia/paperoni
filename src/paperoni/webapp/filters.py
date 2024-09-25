from ..utils import peer_reviewed_release


def no_validation_flag(paper):
    return not any(flag.flag_name == "validation" for flag in paper.paper_flag)


def peer_reviewed(paper):
    return any(peer_reviewed_release(release) for release in paper.releases)
