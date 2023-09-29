def no_validation_flag(paper):
    return not any(flag.flag_name == "validation" for flag in paper.paper_flag)


def peer_reviewed(paper):
    def peer_reviewed_release(release):
        name = release.venue.name.lower()
        return (
            release.status not in ("submitted", "preprint")
            and name
            and name != "n/a"
            and "workshop" not in name
            and "rxiv" not in name
        )

    return any(peer_reviewed_release(release) for release in paper.releases)
