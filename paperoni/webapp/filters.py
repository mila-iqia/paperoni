def no_validation_flag(paper):
    return not any(flag.flag_name == "validation" for flag in paper.paper_flag)
