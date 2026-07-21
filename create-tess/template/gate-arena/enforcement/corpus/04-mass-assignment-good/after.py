ALLOWED_PROFILE_FIELDS = {"display_name", "bio", "avatar_url", "timezone"}


def update_user_profile(user, fields):
    for k, v in fields.items():
        if k in ALLOWED_PROFILE_FIELDS:
            setattr(user, k, v)
    return user
