def update_user_profile(user, fields):
    for k, v in fields.items():
        setattr(user, k, v)
    return user
