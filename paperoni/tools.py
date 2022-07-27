_uuid_tags = ["transient", "canonical"]


def tag_uuid(uuid, status):
    bit = _uuid_tags.index(status)
    nums = list(uuid)
    if bit:
        nums[0] = nums[0] | 128
    else:
        nums[0] = nums[0] & 127
    return bytes(nums)


def get_uuid_tag(uuid):
    return _uuid_tags[(uuid[0] & 128) >> 7]
